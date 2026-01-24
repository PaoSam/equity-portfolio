import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, date

st.set_page_config(page_title="Equity Portfolio Paolo", layout="wide")

def load_equity(uploaded_file):
    data = []
    try:
        content = uploaded_file.getvalue().decode("utf-8")
        for line in content.splitlines():
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    # Carichiamo la data e il PnL
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

st.markdown("### 📈 Equity Portfolio – Paolo")

uploaded_files = st.file_uploader("Carica i file TXT", type="txt", accept_multiple_files=True)

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
        # Trovo i limiti reali dei dati per non far crashare il calendario
        data_min_assoluta = min(all_dates).date()
        data_max_assoluta = max(all_dates).date()
        
        # Limiti del calendario "elastici"
        limite_inferiore = min(data_min_assoluta, date(2010, 1, 1))
        limite_superiore = max(data_max_assoluta, date(2030, 12, 31))

        # --- SELETTORE STRATEGIE ---
        st.write("#### Seleziona Strategie:")
        selected_names = []
        chk_cols = st.columns(min(len(raw_data), 5))
        for i, name in enumerate(sorted(raw_data.keys())):
            with chk_cols[i % 5]:
                if st.checkbox(name, value=True, key=name):
                    selected_names.append(name)

        if selected_names:
            # --- SIDEBAR DATE ---
            st.sidebar.header("Range Temporale")
            
            # Usiamo i limiti calcolati per evitare lo StreamlitAPIException
            start_d = st.sidebar.date_input(
                "Inizio Analisi", 
                value=data_min_assoluta,
                min_value=limite_inferiore,
                max_value=limite_superiore
            )
            end_d = st.sidebar.date_input(
                "Fine Analisi", 
                value=data_max_assoluta,
                min_value=limite_inferiore,
                max_value=limite_superiore
            )

            # Costruzione DataFrame dai PnL
            df_port = pd.DataFrame({'date': sorted(list(set(all_dates)))})
            for name in selected_names:
                df = raw_data[name]
                df_port = df_port.merge(df[['date', 'pnl']].rename(columns={'pnl': name + '_pnl'}), on='date', how='left')
            
            df_port.fillna(0, inplace=True)

            # Filtro temporale dell'utente
            mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
            df_periodo = df_port[mask].copy()

            if df_periodo.empty:
                st.warning("Nessun dato nel periodo selezionato.")
            else:
                # Calcolo Equity che RESETTA a 0 nel periodo scelto
                for name in selected_names:
                    df_periodo[name] = df_periodo[name + '_pnl'].cumsum()
                
                df_periodo['EQUITY_TOTALE'] = df_periodo[selected_names].sum(axis=1)
                df_periodo['drawdown'] = df_periodo['EQUITY_TOTALE'] - df_periodo['EQUITY_TOTALE'].cummax()

                # --- GRAFICO STILE COLAB (Y-AXIS DINAMICA) ---
                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.75, 0.25])

                # Totale
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['EQUITY_TOTALE'], 
                                         name='Equity Totale', line=dict(color='black', width=3)), row=1, col=1)
                # Singole
                for n in selected_names:
                    fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo[n], name=n, line=dict(width=1.2)), row=1, col=1)
                
                # Drawdown
                fig.add_trace(go.Scatter(x=df_periodo['date'], y=df_periodo['drawdown'], name='Drawdown', 
                                         fill='tozeroy', fillcolor='rgba(255, 0, 0, 0.15)',
                                         line=dict(color='red', width=1.5)), row=2, col=1)

                # Fix appiattimento
                fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='rgba(200,200,200,0.3)', row=1, col=1)
                fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='rgba(200,200,200,0.3)', row=2, col=1)
                
                fig.update_layout(
                    plot_bgcolor='white', paper_bgcolor='white', height=750,
                    margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified", uirevision='constant'
                )
                
                st.plotly_chart(fig, use_container_width=True)

                # --- TABELLA PnL ---
                st.write("### PnL Netto Anno per Anno")
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
    st.info("Trascina i file .txt per iniziare l'analisi.")
