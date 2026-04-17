import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# ================= CONFIG =================
USUARIO = 1

def conectar():
    return sqlite3.connect("workflow.db", check_same_thread=False)

conn = conectar()
cursor = conn.cursor()

# ================= ESTILO =================
st.markdown("""
<style>
.card {
    padding: 16px;
    border-radius: 12px;
    background-color: #f5f7fa;
    margin-bottom: 12px;
    box-shadow: 0px 2px 6px rgba(0,0,0,0.1);
}
.title {
    font-size: 18px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# ================= TABELAS =================
cursor.execute("""
CREATE TABLE IF NOT EXISTS Pedido (
    id INTEGER PRIMARY KEY,
    descricao TEXT,
    status_geral TEXT,
    data_criacao DATETIME,
    data_finalizacao DATETIME
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS Fase (
    id INTEGER PRIMARY KEY,
    nome TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS Pedido_Fase (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_id INTEGER,
    fase_id INTEGER,
    status TEXT,
    usuario_id INTEGER,
    data_inicio DATETIME,
    data_fim DATETIME,
    tempo_execucao INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS Log_Fase (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pedido_fase_id INTEGER,
    status_anterior TEXT,
    status_novo TEXT,
    data_alteracao DATETIME,
    usuario_id INTEGER
)
""")

conn.commit()

# ================= SEED =================
def seed():
    cursor.execute("DELETE FROM Pedido")
    cursor.execute("DELETE FROM Pedido_Fase")
    cursor.execute("DELETE FROM Fase")
    cursor.execute("DELETE FROM Log_Fase")

    # fases
    for i in range(1, 6):
        cursor.execute("INSERT INTO Fase VALUES (?, ?)", (i, f"Fase {i}"))

    # pedidos
    for p in range(1, 6):
        cursor.execute("""
        INSERT INTO Pedido VALUES (?, ?, 'ESPERANDO', ?, NULL)
        """, (p, f"Pedido {p}", datetime.now()))

        for f in range(1, 6):
            cursor.execute("""
            INSERT INTO Pedido_Fase (pedido_id, fase_id, status)
            VALUES (?, ?, 'NAO_INICIADA')
            """, (p, f))

    conn.commit()

if "seeded" not in st.session_state:
    seed()
    st.session_state["seeded"] = True

# ================= FUNÇÕES =================

def get_pedidos():
    return pd.read_sql("SELECT * FROM Pedido", conn)

def get_fases(pedido_id):
    return pd.read_sql(f"""
    SELECT pf.*, f.nome
    FROM Pedido_Fase pf
    JOIN Fase f ON pf.fase_id = f.id
    WHERE pf.pedido_id = {pedido_id}
    """, conn)

def get_ultimo_log(pf_id):
    return cursor.execute("""
    SELECT status_novo, data_alteracao
    FROM Log_Fase
    WHERE pedido_fase_id = ?
    ORDER BY id DESC LIMIT 1
    """, (pf_id,)).fetchone()

def atualizar_status_pedido(pedido_id):
    fases = pd.read_sql(f"""
    SELECT status FROM Pedido_Fase
    WHERE pedido_id = {pedido_id}
    """, conn)

    total = len(fases)
    concluidas = len(fases[fases["status"] == "CONCLUIDA"])
    em_andamento = len(fases[fases["status"] == "EM_ANDAMENTO"])

    if concluidas == total:
        cursor.execute("""
        UPDATE Pedido
        SET status_geral='FINALIZADO', data_finalizacao=?
        WHERE id=?
        """, (datetime.now(), pedido_id))

    elif em_andamento > 0:
        cursor.execute("""
        UPDATE Pedido
        SET status_geral='EM_ANDAMENTO'
        WHERE id=?
        """, (pedido_id,))

    else:
        cursor.execute("""
        UPDATE Pedido
        SET status_geral='ESPERANDO'
        WHERE id=?
        """, (pedido_id,))

    conn.commit()

def atualizar_fase(pf_id, novo_status):
    row = cursor.execute("""
    SELECT status, data_inicio, pedido_id FROM Pedido_Fase WHERE id = ?
    """, (pf_id,)).fetchone()

    status_atual, data_inicio, pedido_id = row

    if novo_status == "EM_ANDAMENTO":
        cursor.execute("""
        UPDATE Pedido_Fase
        SET status=?, data_inicio=?, usuario_id=?
        WHERE id=?
        """, (novo_status, datetime.now(), USUARIO, pf_id))

    elif novo_status == "CONCLUIDA":
        fim = datetime.now()
        tempo = int((fim - datetime.fromisoformat(data_inicio)).total_seconds())

        cursor.execute("""
        UPDATE Pedido_Fase
        SET status=?, data_fim=?, tempo_execucao=?
        WHERE id=?
        """, (novo_status, fim, tempo, pf_id))

    # log
    cursor.execute("""
    INSERT INTO Log_Fase (pedido_fase_id, status_anterior, status_novo, data_alteracao, usuario_id)
    VALUES (?, ?, ?, ?, ?)
    """, (pf_id, status_atual, novo_status, datetime.now(), USUARIO))

    conn.commit()

    # atualizar pedido
    atualizar_status_pedido(pedido_id)

# ================= UI =================

st.title("📦 Workflow de Pedidos")

pedidos = get_pedidos()

# -------- LISTA DE PEDIDOS --------
st.subheader("Pedidos")

for _, p in pedidos.iterrows():

    col1, col2 = st.columns([4,1])

    status = p["status_geral"]
    cor = {
        "ESPERANDO": "⚪",
        "EM_ANDAMENTO": "🟡",
        "FINALIZADO": "🟢"
    }[status]

    col1.markdown(f"""
    <div class="card">
        <div class="title">{p['descricao']}</div>
        {cor} {status}
    </div>
    """, unsafe_allow_html=True)

    if col2.button("Abrir", key=f"p_{p['id']}"):
        st.session_state["pedido"] = p["id"]

# -------- DETALHE --------
if "pedido" in st.session_state:

    pedido_id = st.session_state["pedido"]

    st.divider()
    st.subheader(f"📦 Pedido {pedido_id}")

    fases = get_fases(pedido_id)

    # progresso
    total = len(fases)
    concluidas = len(fases[fases["status"] == "CONCLUIDA"])
    st.progress(concluidas / total if total else 0)

    # grid
    cols = st.columns(2)

    for i, (_, row) in enumerate(fases.iterrows()):
        col = cols[i % 2]

        with col:
            cor = {
                "NAO_INICIADA": "⚪",
                "EM_ANDAMENTO": "🟡",
                "CONCLUIDA": "🟢"
            }[row["status"]]

            st.markdown(f"""
            <div class="card">
                <div class="title">{cor} {row['nome']}</div>
            </div>
            """, unsafe_allow_html=True)

            st.write(f"Status: {row['status']}")

            if row["data_inicio"]:
                st.caption(f"Início: {row['data_inicio']}")

            if row["usuario_id"]:
                st.caption(f"Usuário: {row['usuario_id']}")

            if row["data_fim"]:
                st.caption(f"Fim: {row['data_fim']}")

            if row["tempo_execucao"]:
                st.caption(f"Tempo: {row['tempo_execucao']} s")

            # último log
            log = get_ultimo_log(row["id"])
            if log:
                st.caption(f"Último log: {log[0]} ({log[1]})")

            c1, c2 = st.columns(2)

            if c1.button("▶ Iniciar", key=f"s_{row['id']}"):
                if row["status"] == "NAO_INICIADA":
                    atualizar_fase(row["id"], "EM_ANDAMENTO")
                    st.rerun()

            if c2.button("✔ Concluir", key=f"c_{row['id']}"):
                if row["status"] == "EM_ANDAMENTO":
                    atualizar_fase(row["id"], "CONCLUIDA")
                    st.rerun()