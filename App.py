import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date

# Configurazione Pagina
st.set_page_config(page_title="Equity Portfolio Paolo", layout="wide")

# Funzione caricamento dati
def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date_obj = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date_obj, 'pnl': pnl})
                except: continue
    except: return None
    if not data: return None
    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    return df

# --- INTERFACCIA GRAFICA ---
st.markdown("# 📈 Analisi Equity Portfolio")

# Miglioramento grafica caricamento file
st.markdown("---")
st.subheader("📂 Caricamento Dati")
st.info("💡 **Istruzioni**: Carica i file TXT esportati da **Titan** per visualizzare l'analisi aggregata.")

uploaded_files = st.file_uploader(
    "Trascina qui i tuoi file o clicca per selezionarli", 
    type="txt", 
    accept_multiple_files=True,
    help="Seleziona uno o più file .txt esportati da Titan"
)
st.markdown("---")

if uploaded_files:
    raw_data = {}
    all_dates = []
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.extend(df['date'].tolist())

    if raw_data:
        # Limiti dinamici per evitare errori API
        data_min_assoluta = min(all_dates).date()
        data_max_assoluta = max(all_dates).date()
        limite_inferiore = min(data_min_assoluta, date(2010, 1, 1))
        limite_superiore = max(data_max_assoluta, date(2030, 12, 31))

        # --- SELETTORE STRATEGIE ---
        st.write("### 🛠️ Strategie Attive")
        selected_names = []
        chk_cols = st.columns(min(len(raw_data), 4))
        for i, name in enumerate(sorted(raw_data.keys())):
            with chk_cols[i % 4]:
                if st.checkbox(name, value=True, key=name):
                    selected_names.append(name)

        if selected_names:
            # --- SIDEBAR FILTRI ---
            st.sidebar.header("🗓️ Range Temporale")
            start_d = st.sidebar.date_input(
                "Data Inizio Analisi", 
                value=data_min_assoluta,
                min_value=limite_inferiore,
                max_value=limite_superiore
            )
            end_d = st.sidebar.date_input(
                "Data Fine Analisi", 
                value=data_max_assoluta,
                min_value=limite_inferiore,
                max_value=limite_superiore
            )

            # Costruzione DataFrame
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df = raw_data[name]
                df_port = df_port.merge(df[['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            
            df_port.fillna(0, inplace=True)

            # Filtro e ricalcolo da zero
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_periodo = df_port[mask].copy()

            if df_periodo.empty:
                st.warning("⚠️ Nessun dato presente nel periodo selezionato.")
            else:
                for name in selected_names:
                    df_periodo[name] = df_periodo[name + '_pnl'].cumsum()
                
                df_periodo['EQUITY_TOTALE'] = df_periodo[selected_names].sum(axis=1)
                df_periodo['drawdown'] = df_periodo['EQUITY_TOTALE'] - df_periodo['EQUITY_TOTALE'].cummax()

                # --- GRAFICO PROFESSIONALE ---
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

                # Equity Totale
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['EQUITY_TOTALE'], 
                                         name='EQUITY TOTALE', line=dict(color='black', width=3.5)), row=1, col=1)
                # Strategie
                for n in selected_names:
                    fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo[n], name=n, line=dict(width=1.2)), row=1, col=1)
                
                # Drawdown
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['drawdown'], name='Drawdown', 
                                         fill='tozeroy', fillcolor='rgba(231, 76, 60, 0.2)',
                                         line=dict(color='#e74c3c', width=1.5)), row=2, col=1)

                # Styling
                fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='#f0f0f0', row=1, col=1)
                fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='#f0f0f0', row=2, col=1)
                fig.update_xaxes(gridcolor='#f0f0f0')

                fig.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white', height=800,
                    margin=dict(l=20, r=20, t=20, b=20), hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                
                st.plotly_chart(fig, use_container_width=True)

                # --- TABELLA ---
                st.markdown("### 📊 Performance Annuale")
                df_periodo['Year'] = df_periodo['date'].dt.year
                annual_pnl = pd.DataFrame()
                for n in selected_names:
                    annual_pnl[n + ' PnL'] = df_periodo.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
                
                annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
                totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
                annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

                st.table(annual_pnl_with_total.style.apply(lambda x: ['background-color: #d1e7dd; color: black; font-weight: bold' 
                        if x.name == 'TOTALE STORICO' else '' for _ in x], axis=1).format("{:,}"))
else:
    st.info("👋 Benvenuto! Carica i tuoi file TXT da Titan per iniziare l'analisi del portafoglio.")
