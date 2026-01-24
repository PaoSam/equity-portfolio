import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import plotly.graph_objects as go

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Interattivo", layout="wide")

# =============================================
# FUNZIONE CARICAMENTO DATI (Invariata nella logica)
# =============================================
def load_equity(uploaded_file):
    data = []
    try:
        # Leggiamo il contenuto del file caricato
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
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    df['equity'] = df['pnl'].cumsum()
    return df[['date', 'equity', 'pnl']]

# =============================================
# INTERFACCIA STREAMLIT
# =============================================
st.title("### Equity Portfolio Interattivo – Paolo")

# 1. Caricamento File
uploaded_files = st.file_uploader("Carica i tuoi file .txt", type="txt", accept_multiple_files=True)

if uploaded_files:
    equity_dfs = {}
    all_dates = set()

    # Processiamo ogni file caricato
    for uploaded_file in uploaded_files:
        fname = uploaded_file.name
        df = load_equity(uploaded_file)
        if df is not None:
            equity_dfs[fname] = df
            all_dates.update(df['date'])

    if not equity_dfs:
        st.warning("Nessun dato valido estratto dai file.")
    else:
        # Creiamo un dataframe con tutte le date
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})

        equity_columns = []
        pnl_columns = []
        
        for name, df in equity_dfs.items():
            col_name = name.replace('.txt', '').replace('#', '').strip()
            # Merge dell'equity (per grafici) e del pnl (per tabella annuale)
            df_port = df_port.merge(
                df.rename(columns={'equity': col_name, 'pnl': col_name + '_pnl'}),
                on='date', how='left'
            )
            equity_columns.append(col_name)
            pnl_columns.append(col_name + '_pnl')

        # Riempire i buchi
        for p_col in pnl_columns:
            df_port[p_col] = df_port[p_col].fillna(0)
        df_port[equity_columns] = df_port[equity_columns].ffill().fillna(0)

        # ────────────────────────────────────────────────
        # CALCOLO PnL ANNUALE (SOLO MOVIMENTI DELL'ANNO)
        # ────────────────────────────────────────────────
        df_port['Year'] = df_port['date'].dt.year
        years = sorted(df_port['Year'].unique())

        annual_pnl = pd.DataFrame(index=years)

        for col in equity_columns:
            pnl_col_name = col + '_pnl'
            # Somma dei pnl giornalieri dell'anno specifico
            yearly_pnl = df_port.groupby('Year')[pnl_col_name].sum().round(0).astype(int)
            annual_pnl[col + ' PnL'] = yearly_pnl

        # Calcolo Equity Totale: Somma orizzontale dei PnL annuali
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)

        # Aggiunta riga Totale Storico
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        # ────────────────────────────────────────────────
        # GRAFICO INTERATTIVO (Sostituisce Matplotlib per Streamlit)
        # ────────────────────────────────────────────────
        st.subheader("Grafico Equity Portfolio")
        fig = go.Figure()
        
        # Aggiungiamo l'Equity Totale (Somma delle Equity)
        df_port['Total_Equity'] = df_port[equity_columns].sum(axis=1)
        
        fig.add_trace(go.Scatter(x=df_port['date'], y=df_port['Total_Equity'], 
                                 name='EQUITY TOTALE', line=dict(color='white', width=4)))

        for col in equity_columns:
            fig.add_trace(go.Scatter(x=df_port['date'], y=df_port[col], name=col))

        fig.update_layout(template="plotly_dark", height=600, xaxis_title="Data", yaxis_title="Equity")
        st.plotly_chart(fig, use_container_width=True)

        # ────────────────────────────────────────────────
        # TABELLA PnL ANNUALE
        # ────────────────────────────────────────────────
        st.write("---")
        st.subheader("PnL netto prodotto anno per anno (non cumulativo)")
        st.markdown("*Solo i movimenti di quell’anno – Equity_Totale PnL = somma PnL anno corrente*")

        # Funzione per colorare la riga totale e i valori negativi/positivi
        def color_negative_red(val):
            try:
                color = 'red' if val < 0 else '#d1e7dd' # Verde chiaro per positivi
                return f'color: {color}'
            except:
                return ''

        # Visualizzazione tabella stilizzata
        st.dataframe(
            annual_pnl_with_total.style.applymap(color_negative_red).format("{:,}"),
            use_container_width=True
        )

else:
    st.info("In attesa del caricamento dei file .txt per generare l'analisi.")
