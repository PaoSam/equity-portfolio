import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

st.set_page_config(page_title="Equity Portfolio Paolo", layout="wide")

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
                except: continue
    except: return None
    if not data: return None
    df = pd.DataFrame(data)
    df = df.groupby('date')['pnl'].sum().reset_index()
    df = df.sort_values('date')
    df['equity'] = df['pnl'].cumsum()
    return df

st.markdown("### 📈 Equity Portfolio – High Visibility Mode")

uploaded_files = st.file_uploader("Carica i file TXT", type="txt", accept_multiple_files=True)

if uploaded_files:
    raw_data = {}
    all_dates = set()
    for f in uploaded_files:
        name = f.name.replace('.txt', '').replace('#', '').strip()
        df = load_equity(f)
        if df is not None:
            raw_data[name] = df
            all_dates.update(df['date'])

    # Checkbox per ricalcolo totale
    st.write("#### Strategie incluse nel calcolo:")
    selected_names = []
    chk_cols = st.columns(min(len(raw_data), 5))
    for i, name in enumerate(sorted(raw_data.keys())):
        with chk_cols[i % 5]:
            if st.checkbox(name, value=True, key=name):
                selected_names.append(name)

    if selected_names:
        df_port = pd.DataFrame({'date': sorted(list(all_dates))})
        for name in selected_names:
            df = raw_data[name]
            df_port = df_port.merge(df[['date', 'equity', 'pnl']].rename(
                columns={'equity': name, 'pnl': name + '_pnl'}), on='date', how='left')

        df_port[selected_names] = df_port[selected_names].ffill().fillna(0)
        pnl_cols = [n + '_pnl' for n in selected_names]
        df_port[pnl_cols] = df_port[pnl_cols].fillna(0)
        
        df_port['EQUITY_TOTALE'] = df_port[selected_names].sum(axis=1)
        df_port['drawdown'] = df_port['EQUITY_TOTALE'] - df_port['EQUITY_TOTALE'].cummax()

        # Selezione Date
        st.sidebar.header("Range Temporale")
        start_d = st.sidebar.date_input("Inizio", df_port['date'].min())
        end_d = st.sidebar.date_input("Fine", df_port['date'].max())
        
        mask = (df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)
        df_plot = df_port[mask].copy()

        # --- GRAFICO AD ALTA VISIBILITÀ ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_heights=[0.8, 0.2])

        # Equity Totale (Nera)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                 name='Equity Totale', line=dict(color='black', width=3)), row=1, col=1)
        
        for n in selected_names:
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, line=dict(width=1)), row=1, col=1)
        
        # Drawdown (Area Rossa)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], name='Drawdown', 
                                 fill='tozeroy', fillcolor='rgba(255, 0, 0, 0.2)',
                                 line=dict(color='red', width=1)), row=2, col=1)

        # --- CONFIGURAZIONE ASSI PER ZOOM "TIGHT" ---
        # Spieghiamo a Plotly di non includere lo zero forzatamente e di stare stretto sui dati
        fig.update_yaxes(
            autorange=True, 
            fixedrange=False, 
            rangemode="normal", # Permette di ignorare lo zero se i dati sono alti
            gridcolor='lightgrey', 
            zeroline=False,
            row=1, col=1
        )
        
        fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='lightgrey', row=2, col=1)

        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            height=700,
            margin=dict(l=10, r=10, t=10, b=10),
            hovermode="x unified",
            uirevision='constant' # Impedisce il reset dello zoom quando cambi le checkbox
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # Tabella PnL
        st.write("### PnL Netto Anno per Anno")
        df_plot['Year'] = df_plot['date'].dt.year
        annual_pnl = pd.DataFrame()
        for n in selected_names:
            annual_pnl[n + ' PnL'] = df_plot.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
        
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        st.table(annual_pnl_with_total.style.apply(lambda x: ['background-color: #d1e7dd; color: black; font-weight: bold' 
                if x.name == 'TOTALE STORICO' else '' for _ in x], axis=1).format("{:,}"))
