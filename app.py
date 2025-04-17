import streamlit as st
import sqlite3
import os
import bcrypt
import stripe
from datetime import datetime
from PIL import Image

# --- CONFIGURAÇÕES INICIAIS ---
stripe.api_key = os.getenv("STRIPE_API_KEY", "sua_chave_aqui")
st.set_page_config(page_title="E-commerce Completo", layout="wide")
IMAGES_DIR = "images"
os.makedirs(IMAGES_DIR, exist_ok=True)

# --- INJEÇÃO DE CSS ---
st.markdown("""
    <style>
        .title { color: #2E8B57; padding: 20px; }
        .product-card { background: white; padding: 15px; border-radius: 8px; margin: 10px 0; }
        .product-image { max-width: 150px; height: auto; border-radius: 5px; }
        .stButton>button { margin: 5px; }
        .auth-form { background: #f0f2f6; padding: 20px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM BANCO DE DADOS ---
conn = sqlite3.connect('ecommerce.db')
cursor = conn.cursor()

# --- CRIAÇÃO DE TABELAS E MIGRAÇÕES ---
cursor.executescript('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS categorias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS produtos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT,
        preco REAL,
        imagem_url TEXT,
        categoria_id INTEGER,
        media_avaliacoes REAL DEFAULT 0,
        total_avaliacoes INTEGER DEFAULT 0,
        preco_promocional REAL DEFAULT 0,
        FOREIGN KEY(categoria_id) REFERENCES categorias(id)
    );

    CREATE TABLE IF NOT EXISTS carrinho (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        produto_id INTEGER,
        quantidade INTEGER DEFAULT 1,
        data_adicao DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
        FOREIGN KEY(produto_id) REFERENCES produtos(id)
    );

    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        data_pedido DATETIME DEFAULT CURRENT_TIMESTAMP,
        total REAL,
        status TEXT DEFAULT 'pendente',
        payment_intent TEXT,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
    );

    CREATE TABLE IF NOT EXISTS itens_pedido (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER,
        produto_id INTEGER,
        quantidade INTEGER,
        preco_unitario REAL,
        FOREIGN KEY(pedido_id) REFERENCES pedidos(id)
    );

    CREATE TABLE IF NOT EXISTS avaliacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        produto_id INTEGER,
        nota INTEGER,
        comentario TEXT,
        data_avaliacao DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
        FOREIGN KEY(produto_id) REFERENCES produtos(id)
    );
''')

# Migrações (executa apenas se a coluna não existir)
try:
    cursor.execute("ALTER TABLE produtos ADD COLUMN preco_promocional REAL DEFAULT 0")
except sqlite3.OperationalError:
    pass  # Coluna já existe

# Popula dados de exemplo (apague em produção)
cursor.execute('''
    INSERT OR IGNORE INTO produtos (nome, descricao, preco, preco_promocional)
    VALUES ('Smartphone X', 'Celular de última geração', 1999.99, 1799.99)
''')
conn.commit()

# --- INICIALIZAÇÃO DE ESTADO ---
if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 1

# --- AUTENTICAÇÃO ---
with st.sidebar:
    st.header("🔐 Autenticação")
    if st.session_state.user:
        st.write(f"Logado como: **{st.session_state.user['email']}**")
        if st.button("Logout"):
            st.session_state.user = None
            st.rerun()
    else:
        auth_option = st.selectbox("Escolha uma opção", ["Login", "Registrar"])

        if auth_option == "Login":
            email = st.text_input("Email")
            senha = st.text_input("Senha", type="password")
            if st.button("Entrar"):
                user = cursor.execute(
                    "SELECT * FROM usuarios WHERE email = ?",
                    (email,)
                ).fetchone()

                # Correção: Garantir que a senha_hash seja bytes
                if user:
                    senha_hash = user[3]
                    if isinstance(senha_hash, str):
                        senha_hash = senha_hash.encode()

                    if bcrypt.checkpw(senha.encode(), senha_hash):
                        st.session_state.user = {
                            "id": user[0],
                            "email": user[2],
                            "is_admin": user[4]
                        }
                        st.rerun()
                    else:
                        st.error("Usuário ou senha inválidos")
                else:
                    st.error("Usuário ou senha inválidos")

        elif auth_option == "Registrar":
            nome = st.text_input("Nome Completo")
            email = st.text_input("Email")
            senha = st.text_input("Senha", type="password")
            confirmar_senha = st.text_input("Confirmar Senha", type="password")
            if st.button("Registrar"):
                if senha != confirmar_senha:
                    st.error("Senhas não coincidem")
                else:
                    # Correção: Garantir que a senha seja bytes
                    senha_hash = bcrypt.hashpw(senha.encode(), bcrypt.gensalt())
                    try:
                        cursor.execute(
                            "INSERT INTO usuarios (nome, email, senha_hash) VALUES (?, ?, ?)",
                            (nome, email, senha_hash)
                        )
                        conn.commit()
                        st.success("Usuário registrado com sucesso!")
                    except sqlite3.IntegrityError:
                        st.error("Email já cadastrado")

# --- INTERFACE PRINCIPAL ---
st.markdown("<h1 class='title'>🛒 E-commerce Completo</h1>", unsafe_allow_html=True)

# --- SEÇÃO DE ADMINISTRAÇÃO ---
if st.session_state.user and st.session_state.user['is_admin']:
    with st.expander("ADMIN: Gerenciar Categorias"):
        with st.form("categoria_form"):
            nome_categoria = st.text_input("Nova Categoria")
            if st.form_submit_button("Salvar Categoria"):
                try:
                    cursor.execute(
                        "INSERT INTO categorias (nome) VALUES (?)",
                        (nome_categoria,)
                    )
                    conn.commit()
                    st.success("Categoria adicionada!")
                except sqlite3.IntegrityError:
                    st.error("Categoria já existe")

# --- SEÇÃO DE PRODUTOS ---
st.markdown("## 🛍️ Produtos Disponíveis")

# --- FILTROS ---
with st.sidebar:
    st.header("🔍 Filtros")
    search_term = st.text_input("Buscar por nome")
    categoria_filtro = st.selectbox(
        "Filtrar por Categoria",
        ["Todas"] + [c[0] for c in cursor.execute("SELECT nome FROM categorias").fetchall()]
    )
    min_price = st.number_input("Preço Mínimo", value=0.0)
    max_price = st.number_input("Preço Máximo", value=10000.0)

    # Correção: Usar session_state para persistir a página
    page = st.number_input("Página", min_value=1, step=1, value=st.session_state.page)
    st.session_state.page = page

# --- APLICAR FILTROS ---
query = """
    SELECT p.*, c.nome as categoria
    FROM produtos p
    LEFT JOIN categorias c ON p.categoria_id = c.id
    WHERE p.preco BETWEEN ? AND ?
"""
params = [min_price, max_price]

if search_term:
    query += " AND p.nome LIKE ?"
    params.append(f"%{search_term}%")

if categoria_filtro != "Todas":
    query += " AND c.nome = ?"
    params.append(categoria_filtro)

produtos = cursor.execute(query, params).fetchall()
total_pages = max((len(produtos) // 5) + (1 if len(produtos) % 5 > 0 else 0), 1)
page = min(max(page, 1), total_pages)
produtos_pagina = produtos[(page-1)*5 : page*5]

# --- EXIBIÇÃO DE PRODUTOS ---
for produto in produtos_pagina:
    with st.container():
        st.markdown(f"<div class='product-card'>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 3, 2])

        # Coluna da imagem
        with col1:
            # Correção: Melhor tratamento para imagens ausentes
            if produto[4] and os.path.exists(produto[4]):
                st.image(produto[4], width=150)
            else:
                st.write("Sem imagem")

        # Coluna das informações
        with col2:
            st.markdown(f"**{produto[1]}**")
            st.markdown(f"**Preço:** R$ {produto[3]:,.2f}")
            if produto[8] > 0:
                st.markdown(f"🔥 Promo: R$ {produto[8]:,.2f}")
            st.markdown(f"**Descrição:** {produto[2]}")
            st.markdown(f"**Categoria:** {produto[9] or 'Sem categoria'}")

        # Coluna do carrinho
        with col3:
            if st.session_state.user:
                quantidade = st.number_input(
                    f"Quantidade ({produto[1]})",
                    min_value=1,
                    max_value=10,
                    value=1,
                    key=f"qtd_{produto[0]}"
                )
                if st.button(f"🛒 Adicionar ao Carrinho ({produto[1]})", key=f"add_{produto[0]}"):
                    cursor.execute(
                        "INSERT INTO carrinho (usuario_id, produto_id, quantidade) VALUES (?, ?, ?)",
                        (st.session_state.user['id'], produto[0], quantidade)
                    )
                    conn.commit()
                    st.success(f"{quantidade}x {produto[1]} adicionado(s) ao carrinho!")

        st.markdown("</div>", unsafe_allow_html=True)
        st.write("---")

# --- SEÇÃO DE DESTAQUES ---
st.markdown("## 🏆 Destaques")
tabs = st.tabs(["🔥 Mais Vendidos", "⭐ Melhores Avaliados", "💰 Melhores Preços", "🎁 Promoções"])

# --- MAIS VENDIDOS ---
with tabs[0]:
    mais_vendidos = cursor.execute("""
        SELECT p.*, SUM(i.quantidade) as total_vendido
        FROM produtos p
        JOIN itens_pedido i ON p.id = i.produto_id
        GROUP BY p.id
        ORDER BY total_vendido DESC
        LIMIT 5
    """).fetchall()

    if mais_vendidos:
        for produto in mais_vendidos:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if produto[4] and os.path.exists(produto[4]):
                        st.image(produto[4], width=100)
                    else:
                        st.write("Sem imagem")
                with col2:
                    st.write(f"**{produto[1]}**")
                    st.write(f"Vendidos: {produto[10]:,}")
                    st.write(f"Preço: R$ {produto[3]:,.2f}")
    else:
        st.write("Ainda não há produtos vendidos.")

# --- MELHORES AVALIADOS ---
with tabs[1]:
    melhores_avaliados = cursor.execute("""
        SELECT *, (media_avaliacoes * 20) as porcentagem
        FROM produtos
        WHERE total_avaliacoes >= 5
        ORDER BY media_avaliacoes DESC
        LIMIT 5
    """).fetchall()

    if melhores_avaliados:
        for produto in melhores_avaliados:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if produto[4] and os.path.exists(produto[4]):
                        st.image(produto[4], width=100)
                    else:
                        st.write("Sem imagem")
                with col2:
                    st.write(f"**{produto[1]}**")
                    st.write(f"⭐ {produto[6]:.1f}/5 ({produto[7]} avaliações)")
                    st.progress(int(produto[10]))
                    st.write(f"Preço: R$ {produto[3]:,.2f}")
    else:
        st.write("Ainda não há produtos avaliados.")

# --- MELHORES PREÇOS ---
with tabs[2]:
    melhores_precos = cursor.execute("""
        SELECT * FROM produtos
        WHERE preco > 0
        ORDER BY preco ASC
        LIMIT 5
    """).fetchall()

    if melhores_precos:
        for produto in melhores_precos:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if produto[4] and os.path.exists(produto[4]):
                        st.image(produto[4], width=100)
                    else:
                        st.write("Sem imagem")
                with col2:
                    st.write(f"**{produto[1]}**")
                    st.write(f"Preço: R$ {produto[3]:,.2f}")
    else:
        st.write("Não há produtos cadastrados.")

# --- PROMOÇÕES ---
with tabs[3]:
    promocoes = cursor.execute("""
        SELECT * FROM produtos
        WHERE preco_promocional > 0 AND preco_promocional < preco
        ORDER BY (preco - preco_promocional) DESC
        LIMIT 5
    """).fetchall()

    if promocoes:
        for produto in promocoes:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if produto[4] and os.path.exists(produto[4]):
                        st.image(produto[4], width=100)
                    else:
                        st.write("Sem imagem")
                with col2:
                    st.write(f"**{produto[1]}**")
                    st.write(f"Normal: ~~R$ {produto[3]:,.2f}~~")
                    st.write(f"🔥 Promo: R$ {produto[8]:,.2f}")
                    desconto = 100 - (produto[8]/produto[3])*100
                    st.write(f"DESCONTO DE {desconto:.0f}%")
    else:
        st.write("Não há promoções ativas.")

# --- SEÇÃO DE CARRINHO ---
if st.session_state.user:
    with st.expander("🛒 Meu Carrinho"):
        carrinho_itens = cursor.execute(
            """
            SELECT c.id, p.id as produto_id, p.nome, p.preco, c.quantidade, p.imagem_url
            FROM carrinho c
            JOIN produtos p ON c.produto_id = p.id
            WHERE c.usuario_id = ?
            """,
            (st.session_state.user['id'],)
        ).fetchall()

        total = sum(item[3] * item[4] for item in carrinho_itens)

        if carrinho_itens:
            st.write(f"**Total: R$ {total:,.2f}**")

            # Exibir itens do carrinho
            for item in carrinho_itens:
                st.write(f"- {item[2]} ({item[4]}x) - R$ {item[3]:,.2f}")
                if st.button(f"Remover {item[2]}", key=f"rem_{item[0]}"):
                    cursor.execute("DELETE FROM carrinho WHERE id = ?", (item[0],))
                    conn.commit()
                    st.rerun()

            # Correção: Melhor tratamento para pagamento
            if st.button("Finalizar Compra"):
                try:
                    # Criar intent de pagamento
                    intent = stripe.PaymentIntent.create(
                        amount=int(total * 100),
                        currency='brl',
                        payment_method_types=['card'],
                        description=f"Pedido de {st.session_state.user['email']}"
                    )

                    # Criar pedido
                    cursor.execute(
                        "INSERT INTO pedidos (usuario_id, total, payment_intent, status) VALUES (?, ?, ?, ?)",
                        (st.session_state.user['id'], total, intent['id'], 'aguardando_pagamento')
                    )
                    pedido_id = cursor.lastrowid

                    # Adicionar itens ao pedido
                    for item in carrinho_itens:
                        cursor.execute(
                            "INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario) VALUES (?, ?, ?, ?)",
                            (pedido_id, item[1], item[4], item[3])  # Correção: Usar produto_id
                        )

                    # Limpar carrinho
                    cursor.execute(
                        "DELETE FROM carrinho WHERE usuario_id = ?",
                        (st.session_state.user['id'],)
                    )
                    conn.commit()

                    # Correção: Usar link para Stripe em vez de JavaScript
                    st.success(f"Pedido #{pedido_id} criado com sucesso!")
                    st.markdown(f"[Clique aqui para pagar](https://checkout.stripe.com/c/pay/{intent['id']})")

                except Exception as e:
                    st.error(f"Erro no processamento: {str(e)}")
        else:
            st.write("Seu carrinho está vazio")

# --- SEÇÃO DE AVALIAÇÕES ---
if st.session_state.user:
    with st.expander("⭐ Avaliar Produto"):
        produtos = cursor.execute("SELECT id, nome FROM produtos").fetchall()
        if produtos:
            produto_selecionado = st.selectbox("Selecione um produto", produtos, format_func=lambda x: x[1])
            nota = st.slider("Nota", 1, 5)
            comentario = st.text_area("Comentário")

            if st.button("Enviar Avaliação"):
                # Verificar se o usuário comprou o produto
                pedido = cursor.execute(
                    """
                    SELECT 1 FROM itens_pedido
                    JOIN pedidos ON itens_pedido.pedido_id = pedidos.id
                    WHERE pedidos.usuario_id = ? AND itens_pedido.produto_id = ?
                    """,
                    (st.session_state.user['id'], produto_selecionado[0])
                ).fetchone()

                # Verificar se já avaliou
                avaliacao_existente = cursor.execute(
                    "SELECT 1 FROM avaliacoes WHERE usuario_id = ? AND produto_id = ?",
                    (st.session_state.user['id'], produto_selecionado[0])
                ).fetchone()

                if avaliacao_existente:
                    st.error("Você já avaliou este produto")
                elif not pedido:
                    st.error("Você só pode avaliar produtos que já comprou")
                else:
                    cursor.execute(
                        "INSERT INTO avaliacoes (usuario_id, produto_id, nota, comentario) VALUES (?, ?, ?, ?)",
                        (st.session_state.user['id'], produto_selecionado[0], nota, comentario)
                    )
                    cursor.execute(
                        """
                        UPDATE produtos
                        SET media_avaliacoes = (SELECT AVG(nota) FROM avaliacoes WHERE produto_id = ?),
                            total_avaliacoes = (SELECT COUNT(*) FROM avaliacoes WHERE produto_id = ?)
                        WHERE id = ?
                        """,
                        (produto_selecionado[0], produto_selecionado[0], produto_selecionado[0])
                    )
                    conn.commit()
                    st.success("Avaliação registrada!")
        else:
            st.write("Não há produtos para avaliar")

# --- SEÇÃO DE HISTÓRICO DE PEDIDOS ---
if st.session_state.user:
    with st.expander("📜 Meus Pedidos"):
        pedidos = cursor.execute(
            "SELECT * FROM pedidos WHERE usuario_id = ? ORDER BY data_pedido DESC",
            (st.session_state.user['id'],)
        ).fetchall()

        if pedidos:
            for pedido in pedidos:
                with st.container():
                    st.write(f"**Pedido #{pedido[0]}** - {pedido[2]}")
                    st.write(f"Status: {pedido[4]} | Total: R$ {pedido[3]:,.2f}")

                    # Exibir link de pagamento se necessário
                    if pedido[4] == 'aguardando_pagamento' and pedido[5]:
                        st.markdown(f"[Pagar agora](https://checkout.stripe.com/c/pay/{pedido[5]})")

                    itens = cursor.execute(
                        "SELECT p.nome, i.quantidade, i.preco_unitario FROM itens_pedido i JOIN produtos p ON i.produto_id = p.id WHERE i.pedido_id = ?",
                        (pedido[0],)
                    ).fetchall()
                    for item in itens:
                        st.write(f"- {item[0]} ({item[1]}x) - R$ {item[2]:,.2f}")
        else:
            st.write("Você ainda não fez nenhum pedido")

# --- CONTROLES DE PAGINAÇÃO ---
st.write(f"Página {page} de {total_pages}")
prev, _, next_ = st.columns([1, 10, 1])
if prev.button("← Anterior") and page > 1:
    st.session_state.page = page - 1
    st.rerun()
if next_.button("Próximo →") and page < total_pages:
    st.session_state.page = page + 1
    st.rerun()

conn.close()