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

st.markdown("### 📈 Equity Portfolio – Visualizzazione Professionale")

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

    # Checkbox posizionate in alto per ricalcolo istantaneo
    st.write("#### Seleziona Strategie:")
    cols_check = st.columns(max(len(raw_data), 1))
    selected_names = []
    for i, name in enumerate(sorted(raw_data.keys())):
        with cols_check[i % len(cols_check)]:
            if st.checkbox(name, value=True):
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

        # Filtro date per ricalcolo scala
        c1, c2 = st.columns(2)
        start_d = c1.date_input("Inizio", df_port['date'].min())
        end_d = c2.date_input("Fine", df_port['date'].max())
        
        df_plot = df_port[(df_port['date'].dt.date >= start_d) & (df_port['date'].dt.date <= end_d)].copy()

        # --- CREAZIONE GRAFICO STILE COLAB ---
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.02, 
                           row_heights=[0.75, 0.25])

        # Equity Totale (Nera e spessa come in foto)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['EQUITY_TOTALE'], 
                                 name='Equity Totale', line=dict(color='black', width=3)), row=1, col=1)
        
        # Colori per le singole strategie (Cyan e Arancio come in foto)
        colors = ['#00FFFF', '#FFA500', '#00FF00', '#FF00FF']
        for i, n in enumerate(selected_names):
            fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot[n], name=n, 
                                     line=dict(width=1.2, color=colors[i % len(colors)])), row=1, col=1)
        
        # Drawdown (Rosso con riempimento come in foto)
        fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['drawdown'], name='Drawdown', 
                                 fill='tozeroy', fillcolor='rgba(255, 0, 0, 0.1)',
                                 line=dict(color='red', width=1.5)), row=2, col=1)

        # --- SETTAGGI PER EVITARE L'APPIATTIMENTO ---
        fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='lightgrey', gridwidth=0.5, griddash='dot', row=1, col=1)
        fig.update_yaxes(autorange=True, fixedrange=False, gridcolor='lightgrey', gridwidth=0.5, griddash='dot', row=2, col=1)
        fig.update_xaxes(gridcolor='lightgrey', gridwidth=0.5, griddash='dot')

        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='black'),
            height=800,
            margin=dict(l=50, r=50, t=30, b=50),
            hovermode="x unified",
            legend=dict(bgcolor="rgba(255,255,255,0.8)", bordercolor="Black", borderwidth=1)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # Tabella PnL
        st.write("### PnL Netto Anno per Anno")
        df_port['Year'] = df_port['date'].dt.year
        annual_pnl = pd.DataFrame()
        for n in selected_names:
            annual_pnl[n + ' PnL'] = df_plot.groupby('Year')[n + '_pnl'].sum().round(0).astype(int)
        
        annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)
        totale_storico = annual_pnl.sum().rename('TOTALE STORICO')
        annual_pnl_with_total = pd.concat([annual_pnl, totale_storico.to_frame().T])

        st.table(annual_pnl_with_total.style.apply(lambda x: ['background-color: #f0f0f0; font-weight: bold' 
                if x.name == 'TOTALE STORICO' else '' for _ in x], axis=1).format("{:,}"))
