import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Interattivo", layout="wide")

# =============================================
# FUNZIONE CARICAMENTO DATI (Replica fedele)
# =============================================
def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date, 'pnl': pnl})
                except:
                    continue
    except Exception as e:
        st.error(f"Errore lettura {uploaded_file.name}: {e}")
        return None

    if not data:
        return None

    df = pd.DataFrame(data)
    # Raggruppiamo per data come nel tuo codice
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    # Equity cumulativa per i grafici
    df['equity'] = df['pnl'].cumsum()
    return df[['date', 'equity', 'pnl']]

# =============================================
# INTERFACCIA STREAMLIT
# =============================================
st.markdown("### Equity Portfolio Interattivo – Paolo")

# Caricamento file (Sostituisce il bottone di upload di Colab)
uploaded_files = st.file_uploader("Carica i file TXT delle strategie", type="txt", accept_multiple_files=True)

if uploaded_files:
    equity_dfs = {}
    all_dates = set()

    # Estrazione dati (Replica del loop process_and_show)
    for uploaded_file in uploaded_files:
        df = load_equity(uploaded_file)
        if df is not None:
            equity_dfs[uploaded_file.name] = df
            all_dates.update(df['date'])

    if not equity_dfs:
        st.warning("Nessun dato valido estratto dai file.")
    else:
        # Creiamo un dataframe con tutte le date (ordinato)
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})

        equity_columns = []
        pnl_columns = []
        
        for name, df in equity_dfs.items():
            # Pulizia nome come nel tuo codice (.replace('#', ''))
            col_name = name.replace('.txt', '').replace('#', '').strip()
            
            # Merge equity e pnl
            df_port = df_port.merge(
                df.rename(columns={'equity': col_name, 'pnl': col_name + '_pnl'}),
                on='date', how='left'
            )
            equity_columns.append(col_name)
            pnl_columns.append(col_name + '_pnl')

        # Riempimento buchi (ffill per equity, 0 per pnl giornaliero)
        for p_col in pnl_columns:
            df_port[p_col] = df_port[p_col].fillna(0)
        df_port[equity_columns] = df_port[equity_columns].ffill().fillna(0)

        # ────────────────────────────────────────────────
        # CALCOLO PnL ANNUALE (Logica esatta del tuo script)
        # ────────────────────────────────────────────────
        df_port['Year'] = df_port['date'].dt.year
        years = sorted(df_port['Year'].unique())

        annual_pnl = pd.DataFrame(index=years)

        for col in equity_columns:
            pnl_col_name = col + '_pnl'
            # Somma dei pnl giornalieri dell'anno specifico (Round 0 come richiesto)
            yearly_pnl = df_port.groupby('Year')[pnl_col_name].sum().round(0).astype(int)
            annual_pnl[col + ' PnL'] = yearly_pnl

        # Equity_Totale PnL = somma orizzontale dei PnL annuali
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)

        # Aggiunta riga TOTALE STORICO
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        # ────────────────────────────────────────────────
        # GRAFICO (Interattivo con opzione date)
        # ────────────────────────────────────────────────
        st.subheader("Grafico delle Equity")
        
        # Selezione date (DatePicker replicato per Streamlit)
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_d = st.date_input("Data Inizio", value=df_port['date'].min())
        with col_d2:
            end_d = st.date_input("Data Fine", value=df_port['date'].max())

        # Filtro dataframe per grafico
        mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
        df_plot = df_port.loc[mask]

        fig = go.Figure()
        
        # Linea Equity Totale (Somma delle equity correnti)
        total_equity_line = df_plot[equity_columns].sum(axis=1)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=total_equity_line, 
                                 name='EQUITY_TOTALE', line=dict(color='white', width=3)))

        # Linee singole strategie
        for col in equity_columns:
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[col], name=col))

        fig.update_layout(template="plotly_dark", height=600, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        # ────────────────────────────────────────────────
        # TABELLA PnL ANNUALE (Replica visuale)
        # ────────────────────────────────────────────────
        st.markdown("### PnL netto prodotto anno per anno (non cumulativo)")
        st.markdown("*Solo i movimenti di quell’anno – Equity_Totale PnL = somma PnL anno corrente*")

        # Funzione di stile per la riga TOTALE STORICO (Replica highlight_total_row)
        def style_df(df):
            def make_pretty(row):
                if row.name == 'TOTALE STORICO':
                    return ['background-color: #d1e7dd; color: black; font-weight: bold'] * len(row)
                return [''] * len(row)
            return df.style.apply(make_pretty, axis=1).format("{:,}")

        st.table(style_df(annual_pnl_with_total))

else:
    st.info("Trascina qui i file .txt per generare l'analisi.")
