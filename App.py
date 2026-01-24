# app.py

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import io

st.set_page_config(page_title="Equity Portfolio Interattivo", layout="wide")

COLORS = ['cyan', 'orange', 'lime', 'magenta', 'yellow', 'pink', 'lightblue', 'purple']

# ── Cache per non rileggere i file ad ogni interazione ──
@st.cache_data
def parse_txt_file(file_bytes: bytes, filename: str) -> pd.DataFrame | None:
    try:
        lines = file_bytes.decode('utf-8').splitlines()
        data = []
        for line in lines:
            parts = line.strip().split()
            if len(parts) == 6:
                try:
                    date = datetime.strptime(parts[0], '%d/%m/%Y')
                    pnl = float(parts[1])
                    data.append({'date': date, 'pnl': pnl})
                except:
                    continue
        if not data:
            return None
        df = pd.DataFrame(data)
        df = df.groupby('date')['pnl'].sum().reset_index()
        df = df.sort_values('date')
        df['equity'] = df['pnl'].cumsum()
        return df[['date', 'equity', 'pnl']].rename(
            columns={'equity': filename, 'pnl': f"{filename}_pnl"}
        )
    except:
        return None


# =============================================================================
# SIDEBAR - Upload
# =============================================================================
st.sidebar.title("Equity Portfolio")

uploaded_files = st.sidebar.file_uploader(
    "Carica i file .txt delle strategie",
    type=["txt"],
    accept_multiple_files=True,
    help="Carica uno o più file nel formato atteso"
)

if not uploaded_files:
    st.info("Carica almeno un file TXT per iniziare l'analisi.")
    st.stop()

# ── Parsing ────────────────────────────────────────────────────────────────
equity_dfs = {}
all_dates = set()

for file in uploaded_files:
    name = file.name.replace('.txt', '').replace('#', '').strip()
    df = parse_txt_file(file.getvalue(), name)
    if df is not None:
        equity_dfs[name] = df
        all_dates.update(df['date'])

if not equity_dfs:
    st.error("Nessun file ha prodotto dati validi. Controlla il formato.")
    st.stop()

# ── Dataframe unico ────────────────────────────────────────────────────────
df_port = pd.DataFrame({'date': sorted(list(all_dates))})

for name, df in equity_dfs.items():
    df_port = df_port.merge(
        df[['date', name, f"{name}_pnl"]],
        on='date',
        how='left'
    )

df_port[[c for c in df_port.columns if c not in ['date', 'Year']]] = \
    df_port[[c for c in df_port.columns if c not in ['date', 'Year']]].ffill().fillna(0)

for c in df_port.columns:
    if c.endswith('_pnl'):
        df_port[c] = df_port[c].fillna(0)

df_port['Year'] = df_port['date'].dt.year

# ── PnL annuale ────────────────────────────────────────────────────────────
years = sorted(df_port['Year'].unique())
annual_pnl = pd.DataFrame(index=years)

for col in equity_dfs:
    pnl_col = f"{col}_pnl"
    annual_pnl[f"{col} PnL"] = df_port.groupby('Year')[pnl_col].sum().round(0).astype(int)

annual_pnl['Equity_Totale PnL'] = annual_pnl.sum(axis=1).astype(int)

totale = annual_pnl.sum().rename('TOTALE STORICO')
annual_pnl = pd.concat([annual_pnl, totale.to_frame().T])

st.subheader("PnL netto anno per anno (movimenti dell’anno)")
st.markdown("*Equity_Totale PnL = somma dei PnL dell’anno delle strategie selezionate*")

st.dataframe(
    annual_pnl.style
        .format('{:,.0f}')
        .set_properties(**{'text-align': 'center'})
        .apply(lambda row: ['background-color: #d1e7dd; font-weight:bold']*len(row)
               if row.name == 'TOTALE STORICO' else ['']*len(row), axis=1),
    use_container_width=True
)

# =============================================================================
# GRAFICO INTERATTIVO
# =============================================================================
st.subheader("Equity curve + Drawdown")

col1, col2 = st.columns([3,1])

with col1:
    min_date = df_port['date'].min().date()
    max_date = df_port['date'].max().date()

    start_date = st.date_input("Inizio periodo", min_date, min_value=min_date, max_value=max_date)
    end_date   = st.date_input("Fine periodo",   max_date, min_value=min_date, max_value=max_date)

with col2:
    st.write("")  # spacer
    show_total = st.checkbox("Mostra Equity Totale", value=True)

selected_strats = st.multiselect(
    "Strategie da mostrare",
    options=list(equity_dfs.keys()),
    default=list(equity_dfs.keys()),
    placeholder="Seleziona strategie..."
)

if not selected_strats:
    st.warning("Seleziona almeno una strategia per vedere il grafico.")
    st.stop()

# Filtra periodo
mask = (df_port['date'].dt.date >= start_date) & (df_port['date'].dt.date <= end_date)
df_plot = df_port.loc[mask].copy()

if df_plot.empty:
    st.error("Nessun dato nel periodo selezionato.")
    st.stop()

# Normalizza a 0 all'inizio del periodo
for col in selected_strats:
    initial = df_plot[col].iloc[0]
    df_plot[col] = df_plot[col] - initial

df_plot['Equity_Totale_Dynamic'] = df_plot[selected_strats].sum(axis=1)

gain = df_plot['Equity_Totale_Dynamic'].iloc[-1]
st.metric("Gain periodo selezionato", f"{gain:,.0f} $", delta_color="normal")

# Drawdown
df_plot['Peak'] = df_plot['Equity_Totale_Dynamic'].cummax()
df_plot['Drawdown'] = df_plot['Equity_Totale_Dynamic'] - df_plot['Peak']

# ── Plotly ────────────────────────────────────────────────────────────────
fig = go.Figure()

for i, col in enumerate(selected_strats):
    fig.add_trace(go.Scatter(
        x=df_plot['date'], y=df_plot[col],
        name=col,
        line=dict(color=COLORS[i % len(COLORS)]),
        mode='lines'
    ))

if show_total:
    fig.add_trace(go.Scatter(
        x=df_plot['date'], y=df_plot['Equity_Totale_Dynamic'],
        name='Equity Totale',
        line=dict(color='black', width=3.5),
        mode='lines'
    ))

fig.add_trace(go.Scatter(
    x=df_plot['date'], y=df_plot['Drawdown'],
    name='Drawdown',
    line=dict(color='red'),
    fill='tozeroy', fillcolor='rgba(255,0,0,0.1)',
    yaxis='y2'
))

fig.update_layout(
    title="Equity curve (normalizzata al periodo) + Drawdown",
    xaxis_title="Data",
    yaxis_title="Equity ($)",
    yaxis2=dict(
        title="Drawdown",
        overlaying="y",
        side="right",
        showgrid=False,
        titlefont=dict(color="red"),
        tickfont=dict(color="red")
    ),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    height=650
)

st.plotly_chart(fig, use_container_width=True)
