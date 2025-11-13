import streamlit as st
import pandas as pd
from urllib.parse import quote
# CORREÇÃO: Importa o módulo 'datetime' principal para resolver o AttributeError
import datetime 
from datetime import timedelta
import io

# --- Configurações da Aplicação ---
st.set_page_config(layout="wide", page_title="Processador de Clientes Inativos (Reengajamento)")

st.title("🎯 Qualificação para Reengajamento (Clientes Inativos)")
st.markdown("Filtra clientes cuja **última atividade geral** foi **há 30 dias ou mais**.")

# --- Definição das Colunas ---
COL_ID = 'Codigo Cliente'
COL_NAME = 'Cliente'
COL_PHONE = 'Fone Fixo'
COL_STATUS = 'Status' 
COL_ORDER_ID = 'N. Pedido' 
COL_DATE = 'Data' 
COL_TOTAL_VALUE = 'Valor Total' 

# Colunas de SAÍDA
COL_OUT_NAME = 'Cliente_Formatado'
COL_OUT_MSG = 'Mensagem_Personalizada'

# --- Função de Lógica de Negócio (O Cérebro) ---

@st.cache_data
def process_data_inativos(df_input):
    """
    Filtra clientes que tiveram a ÚLTIMA atividade (qualquer status) há 30 dias ou mais.
    """
    df = df_input.copy() 
    
    # 1. Checagem de colunas obrigatórias
    required_cols = [COL_ID, COL_NAME, COL_PHONE, COL_STATUS, COL_ORDER_ID, COL_DATE, COL_TOTAL_VALUE]
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        raise ValueError(f"O arquivo está faltando as seguintes colunas obrigatórias: {', '.join(missing)}. Verifique também a coluna '{COL_DATE}'.")

    metrics = {
        'original_count': len(df),
        'total_pedidos': len(df),
        'clientes_inativos': 0
    }
    
    # 2. Conversão da Data
    try:
        df[COL_DATE] = pd.to_datetime(df[COL_DATE], errors='coerce', dayfirst=True).dt.normalize()
    except Exception as e:
        raise ValueError(f"Erro ao converter a coluna '{COL_DATE}' para data. Erro: {e}")
    
    df.dropna(subset=[COL_DATE], inplace=True)
    
    # --- CORREÇÃO DO ATTRIBUTE ERROR (Linha 58) ---
    today = datetime.datetime.now().normalize()
    date_30_days_ago = today - timedelta(days=30)
    # -----------------------------------
    
    # 3. Lógica Rigorosa de Inatividade (Exclusão Estrita)
    
    # A. Encontra a ÚLTIMA DATA de atividade (qualquer status) para cada cliente
    df_last_activity = df.groupby(COL_ID)[COL_DATE].max().reset_index()
    df_last_activity.rename(columns={COL_DATE: 'Ultima_Atividade_Geral'}, inplace=True)

    # B. Filtra: A última atividade geral DEVE ser de 30 dias atrás ou mais.
    clientes_inativos_ids = df_last_activity[
        df_last_activity['Ultima_Atividade_Geral'] <= date_30_days_ago
    ][COL_ID].unique()

    # C. Aplica o filtro no DataFrame original para obter APENAS os pedidos DESSES clientes
    df_qualified = df[df[COL_ID].isin(clientes_inativos_ids)].copy()
    
    # 4. Seleção Final para Mensagem
    
    # Primeiro, tenta pegar o último pedido 'Enviado'
    df_enviados = df_qualified[df_qualified[COL_STATUS] == 'Enviado'].copy()
    
    if not df_enviados.empty:
        # Usa o último 'Enviado' como referência
        df_final = df_enviados.loc[df_enviados.groupby(COL_ID)[COL_DATE].idxmax()].copy()
    else:
        # Se não há 'Enviado', usa o último pedido de qualquer status (que ainda é inativo)
        df_final = df_qualified.loc[df_qualified.groupby(COL_ID)[COL_DATE].idxmax()].copy()

    # 5. Finalização
    metrics['clientes_inativos'] = len(df_final)
    
    df = df_final.reset_index(drop=True)
    
    if df.empty:
        return df, metrics 
    
    # 6. Criar mensagem personalizada
    
    def format_name_and_create_message(row):
        """Formata o nome e cria a mensagem."""
        full_name = row[COL_NAME]
        last_order_date = row[COL_DATE].strftime('%d/%m/%Y')
        
        if not full_name:
            first_name = "Cliente"
        else:
            full_name_str = str(full_name).strip()
            first_name = full_name_str.split(' ')[0] 
            first_name = first_name.capitalize() 
            
        # Determina o status para usar na mensagem
        status_ref = 'compra' if row[COL_STATUS] == 'Enviado' else 'atividade'
            
        # --- TEMPLATE PADRÃO DE REENGAJAMENTO ---
        message = (
            f"Olá {first_name}! Aqui é o Victor da *Jumbo CDP!* \n"
            f"Vimos que sua última {status_ref} foi em {last_order_date}. Estamos com saudades! \n\n"
            f"Para comemorar sua próxima compra, conseguimos um **BRINDE EXCLUSIVO** para o seu próximo pedido. \n\n"
            f"Me avise se posso te contar a novidade rapidinho!"
        )
        # ----------------------------------
        
        return first_name, message

    # --- ATRIBUIÇÃO DE COLUNAS ---
    
    df[COL_NAME] = df[COL_NAME].astype(str).fillna('')
    
    data_series = df.apply(format_name_and_create_message, axis=1)

    temp_df = pd.DataFrame(data_series.tolist(), index=df.index) 
    
    df[COL_OUT_NAME] = temp_df[0]
    df[COL_OUT_MSG] = temp_df[1]
    
    # 7. Formatar valor total e data para exibição
    def format_brl(value):
        try:
            value_str = str(value).replace('R$', '').replace('.', '').replace(',', '.')
            return f"R$ {float(value_str):.2f}".replace('.', ',')
        except:
            return str(value)

    df['Valor_BRL'] = df[COL_TOTAL_VALUE].apply(format_brl)
    df['Data_Referencia'] = df[COL_DATE].dt.strftime('%d/%m/%Y')
    
    return df, metrics

# --- Interface do Usuário (Streamlit) ---

# Seção de Upload
st.header("1. Upload do Relatório de Vendas (Excel/CSV)")
st.markdown(f"#### Colunas Esperadas: {COL_ID}, {COL_NAME}, {COL_PHONE}, {COL_STATUS}, {COL_ORDER_ID}, **{COL_DATE}**, {COL_TOTAL_VALUE}")

uploaded_file = st.file_uploader(
    "Arraste ou clique para enviar o arquivo.", 
    type=["csv", "xlsx"]
)

if uploaded_file is not None:
    # ... (Resto do código da interface permanece o mesmo) ...
    try:
        if uploaded_file.name.endswith('.csv'):
            df_original = pd.read_csv(uploaded_file)
        else:
            df_original = pd.read_excel(uploaded_file, engine='openpyxl')
            
        st.success(f"Arquivo '{uploaded_file.name}' carregado com sucesso!")
        
    except Exception as e:
        st.error(f"Erro ao ler o arquivo. Erro: {e}")
        st.stop()


    # Botão de Processamento
    st.header("2. Iniciar Qualificação de Reengajamento")
    if st.button("🚀 Processar Dados e Gerar Leads Inativos"):
        
        try:
            df_processed, metrics = process_data_inativos(df_original)
        except ValueError as ve:
            st.error(f"Erro de Processamento: {ve}")
            st.stop()
        
        # --- Seção de Resultados ---
        st.header("3. Lista de Disparo com BRINDE (Clientes Inativos)")
        
        col_met1, col_met2, col_met3 = st.columns(3)
        col_met1.metric("Clientes Originais", metrics['original_count'])
        col_met2.metric("Total de Pedidos", metrics['total_pedidos'])
        col_met3.metric("Clientes Inativos (30+ dias)", metrics['clientes_inativos'])
        
        total_ready = len(df_processed)
        st.subheader(f"Leads para Reengajamento ({total_ready} Clientes)")
        
        if total_ready == 0:
            st.info("Nenhum lead encontrado com o perfil: Última atividade há 30 dias ou mais.")
        else:
            st.markdown("---")
            st.markdown("#### Clique no botão para iniciar o contato de reengajamento no WhatsApp.")
            
            # Cria o layout da tabela de botões
            col_headers = st.columns([1.5, 1.5, 1.5, 5]) 
            col_headers[0].markdown("**Nome**")
            col_headers[1].markdown(f"**Data de Referência**") 
            col_headers[2].markdown(f"**{COL_TOTAL_VALUE}**") 
            col_headers[3].markdown("**Ação (Disparo de Reengajamento)**")
            st.markdown("---")
            
            # Itera sobre os leads qualificados
            for index, row in df_processed.iterrows():
                cols = st.columns([1.5, 1.5, 1.5, 5]) 
                
                first_name = row[COL_OUT_NAME]
                
                # Prepara o número de telefone (remove tudo exceto dígitos)
                phone_raw = str(row[COL_PHONE])
                phone_number = "".join(filter(str.isdigit, phone_raw))

                message_text = row[COL_OUT_MSG]
                last_order_date = row['Data_Referencia']
                valor_brl = row['Valor_BRL'] 
                
                # Cria o link oficial do WhatsApp, codificando a mensagem
                encoded_message = quote(message_text)
                whatsapp_link = f"https://wa.me/55{phone_number}?text={encoded_message}"
                
                # 1. Exibe os dados
                cols[0].write(first_name)
                cols[1].write(last_order_date)
                cols[2].write(valor_brl)
                
                # 2. Cria e exibe o botão
                button_label = f"WhatsApp para {first_name}"
                button_html = f"""
                <a href="{whatsapp_link}" target="_blank" style="
                    display: inline-block; 
                    padding: 8px 12px; 
                    background-color: #34B7F1; 
                    color: white; 
                    text-align: center; 
                    text-decoration: none; 
                    border-radius: 4px; 
                    border: 1px solid #1E90FF;
                    cursor: pointer;
                    white-space: nowrap;
                ">
                {button_label}
                </a>
                """
                cols[3].markdown(button_html, unsafe_allow_html=True)

            st.markdown("---")

            # Botão de Download
            df_export = df_processed[[COL_ID, COL_NAME, COL_PHONE, COL_STATUS, COL_ORDER_ID, COL_TOTAL_VALUE, 'Data_Referencia', COL_OUT_MSG]].copy()
            df_export.rename(columns={COL_DATE: 'Data_Pedido_Referencia', 'Data_Referencia': 'Ultima_Atividade_no_Filtro'}, inplace=True)
            
            # Formata para CSV
            csv_data = df_export.to_csv(index=False, sep=';', encoding='utf-8').encode('utf-8')
            st.download_button(
                label="📥 Baixar Lista de Clientes Inativos (CSV)",
                data=csv_data,
                file_name='clientes_inativos_para_reengajamento.csv',
                mime='text/csv',
            )
