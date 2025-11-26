import streamlit as st
import pandas as pd
from urllib.parse import quote
# CORREÇÃO FINAL: Usamos date e timedelta, a forma mais estável de importar data no Streamlit
from datetime import date, timedelta 
import datetime 
import io

# --- Configurações da Aplicação ---
st.set_page_config(layout="wide", page_title="Processador de Clientes Inativos (Reengajamento)")

st.title("🎯 Qualificação para Reengajamento (Clientes Inativos)")
st.markdown("Filtra clientes que foram compradores e cuja **última atividade geral** foi **exatamente 28 dias atrás**.")

# --- Definição das Colunas ---
COL_ID = 'Codigo Cliente'
COL_NAME = 'Cliente'
COL_PHONE = 'Fone Fixo'
COL_STATUS = 'Status' 
COL_ORDER_ID = 'N. Pedido' 
COL_DATE = 'Data' 
COL_TOTAL_VALUE = 'Valor Total' 
COL_DETENTO = 'Ultimo Detento Cadastrado' 

# Colunas de SAÍDA
COL_OUT_NAME = 'Cliente_Formatado'
COL_OUT_MSG = 'Mensagem_Personalizada'

# --- Lógica de Gênero ---
FEMININE_NAMES = {
    'maria', 'ana', 'paula', 'carla', 'patricia', 'gabriela', 'juliana', 
    'fernanda', 'aline', 'bruna', 'camila', 'leticia', 'isabela', 'sofia', 
    'beatriz', 'vitoria', 'claudia', 'elena', 'raquel', 'sandra', 'valeria',
    'marcia', 'monica', 'larissa', 'eduarda', 'helena', 'regina', 'viviane', 'luciana'
}

def get_gender_parts(first_name):
    """Retorna o pronome, preposição e artigo definido com base no primeiro nome."""
    lower_name = first_name.lower()
    
    if lower_name in FEMININE_NAMES or (lower_name.endswith('a') and len(lower_name) > 2):
        return {'pronoun': 'ela', 'preposition': 'da', 'article': 'a'}
    
    return {'pronome': 'ele', 'preposition': 'do', 'article': 'o'}


# --- Função de Lógica de Negócio (O Cérebro) ---

@st.cache_data
def process_data_inativos(df_input):
    """
    Filtra clientes que tiveram a ÚLTIMA atividade (qualquer status) há EXATAMENTE 28 dias, 
    e que essa última atividade tenha sido um pedido 'Enviado' (Cliente Comprador).
    """
    df = df_input.copy() 
    
    # 1. Checagem de colunas obrigatórias
    required_cols = [COL_ID, COL_NAME, COL_PHONE, COL_STATUS, COL_ORDER_ID, COL_DATE, COL_TOTAL_VALUE, COL_DETENTO]
    if not all(col in df.columns for col in required_cols):
        missing = [col for col in required_cols if col not in df.columns]
        raise ValueError(f"O arquivo está faltando as seguintes colunas obrigatórias: {', '.join(missing)}. Verifique '{COL_DETENTO}'.")

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
    
    # --- CÁLCULO DE INATIVIDADE (CORREÇÃO DE DATA/TEMPO) ---
    today = date.today() 
    date_28_days_ago = today - timedelta(days=28)
    # -----------------------------------
    
    # 3. Lógica Rigorosa de Inatividade (Exclusão Estrita)
    
    # A. Encontra a ÚLTIMA DATA de atividade (qualquer status) para cada cliente
    df_last_activity = df.groupby(COL_ID)[COL_DATE].max().reset_index()
    df_last_activity.rename(columns={COL_DATE: 'Ultima_Atividade_Geral'}, inplace=True)

    # B. Filtra: A última atividade geral DEVE ser de EXATAMENTE 28 dias atrás.
    clientes_inativos_ids = df_last_activity[
        df_last_activity['Ultima_Atividade_Geral'].dt.date == date_28_days_ago
    ][COL_ID].unique()

    # C. Aplica o filtro no DataFrame original para obter APENAS os pedidos DESSES clientes
    df_qualified = df[df[COL_ID].isin(clientes_inativos_ids)].copy()
    
    # 4. Seleção Final para Mensagem (Última atividade deve ser 'Enviado')
    
    # Merge para ligar a data da última atividade com o status do pedido
    df_final_check = df_qualified.merge(
        df_last_activity, 
        on=COL_ID, 
        how='left'
    )

    # FILTRO ESTRITO: MANTÉM apenas os clientes onde a última atividade geral
    # TEM o status 'Enviado' atrelado a essa data.
    df_target = df_final_check[
        (df_final_check[COL_DATE] == df_final_check['Ultima_Atividade_Geral']) & 
        (df_final_check[COL_STATUS] == 'Enviado')
    ].copy()

    # Garantir uma única linha por cliente (o registro mais recente que atende aos critérios)
    df_final = df_target.drop_duplicates(subset=[COL_ID], keep='first').copy()
    
    # 5. Finalização
    metrics['clientes_inativos'] = len(df_final)
    
    df = df_final.reset_index(drop=True)
    
    if df.empty:
        return df, metrics 
    
    # 6. Criar mensagem personalizada
    
    def format_name_and_create_message(row):
        """Formata o nome do CLIENTE para saudação e do DETENTO para o corpo da mensagem, incluindo gênero."""
        cliente_full_name = row[COL_NAME]
        detento_full_name = row[COL_DETENTO]
        last_order_date = row[COL_DATE].strftime('%d/%m/%Y')
        
        # 1. Saudação (Usa o primeiro nome do CLIENTE)
        if not cliente_full_name:
            client_first_name = "Cliente"
        else:
            client_first_name = str(cliente_full_name).strip().split(' ')[0] 
            client_first_name = client_first_name.capitalize() 

        # 2. Personalização (Usa o primeiro nome do DETENTO e determina o GÊNERO)
        if not detento_full_name or pd.isna(detento_full_name):
            detento_first_name = "a pessoa amada" 
            pronome = "ele/ela" 
            artigo_definido = "o/a"
        else:
            detento_first_name = str(detento_full_name).strip().split(' ')[0]
            detento_first_name = detento_first_name.capitalize()
            
            gender_parts = get_gender_parts(detento_first_name) 
            pronome = gender_parts['pronoun']
            artigo_definido = gender_parts['article'] 

        # --- TEMPLATE DE MENSAGEM FINAL (COM ARTIGO DEFINIDO CORRIGIDO) ---
        message = (
            f"Olá {client_first_name}! Aqui é o Victor da *Jumbo CDP!* \n"
            f"Tenho uma ótima notícia para você.\n\n"
            f"Notamos que o seu último jumbo para {artigo_definido} {detento_first_name} foi em {last_order_date} — {pronome} pode estar a precisar de alguns produtos!\n\n"
            f"Para celebrar a sua próxima compra, consegui garantir um *BRINDE EXCLUSIVO* para incluir no pedido d{artigo_definido} {detento_first_name}.\n\n"
            f"Posso te contar rapidinho qual é a surpresa? É só me avisar!"
        )
        # ----------------------------------
        
        # Retorna o nome do CLIENTE para a coluna Cliente_Formatado
        return client_first_name, message

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
st.markdown(f"#### Colunas Esperadas: {COL_ID}, {COL_NAME}, {COL_PHONE}, {COL_STATUS}, {COL_ORDER_ID}, **{COL_DATE}**, {COL_TOTAL_VALUE}, **{COL_DETENTO}**")

uploaded_file = st.file_uploader(
    "Arraste ou clique para enviar o arquivo.", 
    type=["csv", "xlsx"]
)

if uploaded_file is not None:
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
        col_met3.metric("Clientes Inativos (28 dias exatos)", metrics['clientes_inativos'])
        
        total_ready = len(df_processed)
        st.subheader(f"Leads para Reengajamento ({total_ready} Clientes)")
        
        if total_ready == 0:
            st.info("Nenhum lead encontrado com o perfil: Última **compra enviada** há **exatos 28 dias**.")
        else:
            st.markdown("---")
            st.markdown("#### Clique no botão para iniciar o contato de reengajamento no WhatsApp.")
            
            # --- Ajuste das Colunas da Tabela ---
            col_headers = st.columns([1.5, 1.5, 1.2, 1.2, 1.2, 5]) 
            col_headers[0].markdown("**Cliente**") 
            col_headers[1].markdown(f"**Detento**") 
            col_headers[2].markdown(f"**Data Ref.**") 
            col_headers[3].markdown(f"**{COL_TOTAL_VALUE}**") 
            col_headers[4].markdown(f"**N. Pedido**") 
            col_headers[5].markdown("**Ação (Disparo de Reengajamento)**")
            st.markdown("---")
            
            # Itera sobre os leads qualificados
            for index, row in df_processed.iterrows():
                # Colunas ajustadas
                cols = st.columns([1.5, 1.5, 1.2, 1.2, 1.2, 5]) 
                
                cliente_first_name = row[COL_OUT_NAME] # Nome do Cliente para a coluna
                
                # Prepara os dados
                detento_name_clean = row[COL_DETENTO].split(' ')[0].capitalize() if row[COL_DETENTO] else "Sem Detento"
                
                phone_raw = str(row[COL_PHONE])
                phone_number = "".join(filter(str.isdigit, phone_raw))
                message_text = row[COL_OUT_MSG]
                last_order_date = row['Data_Referencia']
                valor_brl = row['Valor_BRL'] 
                order_number = row[COL_ORDER_ID] 
                
                # Cria o link oficial do WhatsApp, codificando a mensagem
                encoded_message = quote(message_text)
                whatsapp_link = f"https://wa.me/55{phone_number}?text={encoded_message}"
                
                # 1. Exibe os dados
                cols[0].write(cliente_first_name) # Mostra o Cliente
                cols[1].write(detento_name_clean)      # Mostra o Detento
                cols[2].write(last_order_date)
                cols[3].write(valor_brl)
                cols[4].write(order_number) 
                
                # 2. Cria e exibe o botão (COR AZUL)
                button_label = f"WhatsApp Reeng. para {cliente_first_name}"
                button_html = f"""
                <a href="{whatsapp_link}" target="_blank" style="
                    display: inline-block; 
                    padding: 8px 12px; 
                    background-color: #34B7F1; /* Azul Claro para diferenciar */
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
                cols[5].markdown(button_html, unsafe_allow_html=True) # Exibe o botão na nova coluna 5

            st.markdown("---")

            # Botão de Download
            df_export = df_processed[[COL_ID, COL_NAME, COL_DETENTO, COL_PHONE, COL_STATUS, COL_ORDER_ID, COL_TOTAL_VALUE, 'Data_Referencia', COL_OUT_MSG]].copy()
            df_export.rename(columns={COL_DATE: 'Data_Pedido_Referencia', 'Data_Referencia': 'Ultima_Atividade_no_Filtro'}, inplace=True)
            
            # Formata para CSV
            csv_data = df_export.to_csv(index=False, sep=';', encoding='utf-8').encode('utf-8')
            st.download_button(
                label="📥 Baixar Lista de Clientes Inativos (CSV)",
                data=csv_data,
                file_name='clientes_inativos_para_reengajamento.csv',
                mime='text/csv',
            )
