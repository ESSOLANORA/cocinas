"""
Planificador de Recetas — app.py
Multi-usuario · Favoritos · Listas de ingredientes · Filtro exacto/+N
"""
import streamlit as st
import pandas as pd
import re
import json
from pathlib import Path
from collections import Counter

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="🍽️ Planificador de Recetas",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_DIR   = Path("data")
USERS_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(exist_ok=True)

DIAS       = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MEAL_SLOTS = ["🌅 Desayuno", "☀️ Comida", "🌙 Cena"]
AVATARS    = ["👤","👨","👩","👦","👧","🧑","👴","👵","🧔","👶",
              "🐱","🐶","🦊","🐻","🐼","🐨","🦁","🐯","🐸","🦄"]

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { padding-top: 0.5rem; }
.main .block-container { padding: 0.5rem 1.2rem 2rem; max-width: 980px; }
[data-testid="stTabs"] button { font-size: 0.82rem; padding: 0.35rem 0.7rem; }

.profile-bar {
    display:flex; align-items:center; gap:10px;
    background:#f0f4ff; border-radius:10px;
    padding:0.5rem 1rem; margin-bottom:1rem;
}
.profile-name { font-weight:700; font-size:1rem; color:#1a1a2e; }

.recipe-badge {
    display:inline-block; background:#e8f4fd; color:#1565c0;
    border-radius:6px; padding:2px 8px; font-size:0.7rem;
    margin-right:3px; margin-top:3px;
}
.fav-badge {
    display:inline-block; background:#fff3cd; color:#856404;
    border-radius:6px; padding:2px 8px; font-size:0.7rem;
}
.day-header {
    background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
    color:white; padding:0.45rem 0.7rem;
    border-radius:8px 8px 0 0; font-weight:600; font-size:0.85rem;
}
.day-box {
    border:1px solid #e0e0e0; border-top:none;
    border-radius:0 0 8px 8px; padding:0.5rem;
    min-height:75px; background:white; margin-bottom:0.4rem;
}
.planned-recipe {
    background:#f0fdf4; border:1px solid #86efac;
    border-radius:5px; padding:3px 7px;
    font-size:0.75rem; margin:2px 0; color:#166534;
}
.list-card {
    background:#f8f9fa; border:1px solid #dee2e6;
    border-radius:10px; padding:0.8rem; margin-bottom:0.6rem;
}
.list-title { font-weight:700; font-size:0.95rem; color:#1a1a2e; }
.shop-cat { font-weight:700; color:#7c3aed; margin-top:0.8rem; font-size:0.88rem; }
.stars { color:#f59e0b; font-size:0.82rem; }
footer { visibility:hidden; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# GESTIÓN DE USUARIOS (JSON)
# ══════════════════════════════════════════════════════════════════════════════
def load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}

def save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")

def user_file(username: str) -> Path:
    safe = re.sub(r"[^\w\-]", "_", username.lower())
    return DATA_DIR / f"user_{safe}.json"

def load_user_data(username: str) -> dict:
    f = user_file(username)
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {
        "planner":    {d: [] for d in DIAS},
        "favorites":  [],           # list of recipe titles
        "ing_lists":  {},           # {"Nevera": ["pollo","arroz",...], ...}
    }

def save_user_data(username: str, data: dict):
    user_file(username).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

# shortcut helpers on session state
def ud() -> dict:
    return st.session_state.user_data

def save_ud():
    save_user_data(st.session_state.current_user, ud())

# ══════════════════════════════════════════════════════════════════════════════
# INGREDIENT / DATASET HELPERS
# ══════════════════════════════════════════════════════════════════════════════
_UNIT_RE = re.compile(
    r"^(?:kilogramo[s]?|gramo[s]?|litro[s]?|mililitro[s]?|cucharadas?\s+soperas?|"
    r"cucharadas?\s+postres?|cucharada[s]?|cucharadita[s]?|cucharón[es]?|taza[s]?|"
    r"vaso[s]?|copa[s]?|lata[s]?|unidad[es]?|pieza[s]?|trozo[s]?|rama[s]?|"
    r"manojo[s]?|pizca[s]?|chorro[s]?|puñado[s]?|rebanada[s]?|centímetro[s]?|"
    r"diente[s]?|paquete[s]?|sobre[s]?|pellizco[s]?|atado[s]?|cabeza[s]?|"
    r"loncha[s]?)\s+(?:de\s+)?",
    re.IGNORECASE,
)

def _clean_token(item: str) -> str:
    item = re.sub(r"^[\d½¼¾/.,\s]+", "", item)
    item = _UNIT_RE.sub("", item)
    item = re.sub(r"^(?:sopera[s]?|postre[s]?)\s+de\s+", "", item, flags=re.IGNORECASE)
    item = re.sub(r"^de\s+", "", item, flags=re.IGNORECASE)
    item = re.sub(r"\s*\(.*?\)", "", item)
    item = re.sub(r"\s+al\s+gusto.*$", "", item)
    return item.strip().lower()

def _tokenize(ing_str: str) -> list:
    if not ing_str:
        return []
    out = []
    for item in ing_str.split(" | "):
        t = _clean_token(item.strip())
        if len(t) > 2 and not t.startswith("##") and not t.startswith("para"):
            out.append(t)
    return out

def parse_display(ing_str: str) -> list:
    if not ing_str:
        return []
    return [i.strip() for i in ing_str.split(" | ")
            if i.strip() and not i.strip().startswith("##")]

def time_to_min(t: str) -> int:
    if not t:
        return 9999
    m = re.match(r"(?:(\d+)h\s*)?(?:(\d+)m)?", t)
    return (int(m.group(1) or 0) * 60 + int(m.group(2) or 0)) if m else 9999

def stars(r: float) -> str:
    n = int(round(r))
    return "★" * n + "☆" * (5 - n)

# ── Dataset loading ────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando recetas…")
def load_data(path: str) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(path, encoding=enc, low_memory=False); break
            except UnicodeDecodeError:
                continue
    else:
        df = pd.read_excel(path, engine="openpyxl")
    df["titulo"]           = df["titulo"].fillna("Sin título")
    df["categoria"]        = df["categoria"].fillna("Otras")
    df["dificultad"]       = df["dificultad"].fillna("Sin datos")
    df["tiempo_total"]     = df["tiempo_total"].fillna("")
    df["comensales"]       = pd.to_numeric(df["comensales"], errors="coerce").fillna(4).astype(int)
    df["valoracion_media"] = pd.to_numeric(df["valoracion_media"], errors="coerce").fillna(0)
    df["calorias"]         = pd.to_numeric(df["calorias"], errors="coerce").fillna(0)
    df["ingredientes"]     = df["ingredientes"].fillna("")
    df["imagen_url"]       = df.get("imagen_url", pd.Series([""] * len(df))).fillna("")
    df["_tokens"]          = df["ingredientes"].apply(_tokenize)
    return df

@st.cache_data(show_spinner="Indexando ingredientes…")
def build_vocab(_df: pd.DataFrame) -> tuple:
    try:
        from rapidfuzz import fuzz, process
        fuzzy = True
    except ImportError:
        fuzzy = False

    counter: Counter = Counter()
    for t in _df["_tokens"]: counter.update(t)
    vocab = sorted([k for k, v in counter.items() if v >= 3], key=lambda x: -counter[x])

    if not fuzzy:
        return {t: t for t in vocab}, sorted(vocab)

    cmap, assigned = {}, set()
    for term in vocab:
        if term in assigned: continue
        hits = process.extract(term, vocab, scorer=fuzz.token_sort_ratio, limit=12, score_cutoff=83)
        group = [h[0] for h in hits if h[0] not in assigned] or [term]
        canon = max(group, key=lambda x: counter.get(x, 0))
        for v in group: cmap[v] = canon
        assigned.update(group)
    return cmap, sorted(set(cmap.values()))

@st.cache_data(show_spinner=False)
def canonical_token_col(_df: pd.DataFrame, _cmap: dict) -> pd.Series:
    return _df["_tokens"].apply(lambda toks: list({_cmap.get(t, t) for t in toks}))

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — dataset upload
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Dataset")
    uploaded = st.file_uploader("Cargar dataset", type=["xlsx", "csv"])
    dataset_path = None
    if uploaded:
        ext = Path(uploaded.name).suffix.lower()
        sname = f"dataset{ext}"
        Path(sname).write_bytes(uploaded.read())
        dataset_path = sname
        st.success(f"✓ {uploaded.name}")
    st.caption("O coloca `dataset.csv` / `dataset.xlsx` junto a `app.py`.")

if not dataset_path:
    for c in ["dataset.csv", "dataset.xlsx"]:
        if Path(c).exists():
            dataset_path = c; break

# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════
if not dataset_path:
    st.title("🍽️ Planificador de Recetas")
    st.info("👆 Sube tu dataset desde el menú lateral para empezar.")
    st.stop()

try:
    df = load_data(dataset_path)
except Exception as e:
    st.error(f"Error cargando dataset: {e}"); st.stop()

cmap, canon_list = build_vocab(df)
df["_ctokens"] = canonical_token_col(df, cmap)

# ══════════════════════════════════════════════════════════════════════════════
# PROFILE SELECTOR — cabecera
# ══════════════════════════════════════════════════════════════════════════════
users = load_users()

hcol1, hcol2, hcol3 = st.columns([3, 2, 2])
with hcol1:
    st.title("🍽️ Planificador de Recetas")
with hcol2:
    user_names = list(users.keys())
    options = user_names + ["＋ Nuevo perfil"]
    # Restore last selection
    default_idx = 0
    if "current_user" in st.session_state and st.session_state.current_user in user_names:
        default_idx = user_names.index(st.session_state.current_user)

    sel = st.selectbox(
        "👤 Perfil",
        options=options,
        index=default_idx,
        label_visibility="collapsed",
    )
with hcol3:
    if sel != "＋ Nuevo perfil" and sel in users:
        avatar = users[sel].get("avatar", "👤")
        st.markdown(
            f'<div class="profile-bar">'
            f'<span style="font-size:1.6rem">{avatar}</span>'
            f'<span class="profile-name">{sel}</span></div>',
            unsafe_allow_html=True,
        )

# ── Create new profile ─────────────────────────────────────────────────────────
if sel == "＋ Nuevo perfil":
    st.markdown("### Crear perfil")
    nc1, nc2, nc3 = st.columns([3, 2, 1])
    with nc1:
        new_name = st.text_input("Nombre", placeholder="Tu nombre…", key="new_name_input")
    with nc2:
        new_avatar = st.selectbox("Avatar", AVATARS, key="new_avatar_sel")
    with nc3:
        st.write("")
        st.write("")
        if st.button("Crear", type="primary"):
            if new_name.strip():
                nname = new_name.strip()
                users[nname] = {"avatar": new_avatar}
                save_users(users)
                st.session_state.current_user = nname
                st.session_state.user_data = load_user_data(nname)
                st.rerun()
            else:
                st.warning("Escribe un nombre.")
    st.info("Selecciona un perfil existente o crea uno nuevo para continuar.")
    st.stop()

# ── Activate selected profile ──────────────────────────────────────────────────
if not users:
    st.info("No hay perfiles todavía. Crea el primero con el desplegable de arriba.")
    st.stop()

current_user = sel
if (st.session_state.get("current_user") != current_user):
    st.session_state.current_user = current_user
    st.session_state.user_data    = load_user_data(current_user)

if "user_data" not in st.session_state:
    st.session_state.user_data = load_user_data(current_user)

st.caption(
    f"📊 {len(df):,} recetas · {df['categoria'].nunique()} categorías · "
    f"{len(canon_list):,} ingredientes indexados · "
    f"Perfil: **{users[current_user].get('avatar','👤')} {current_user}**"
)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
    ["📅 Planner", "🔍 Explorar", "⭐ Favoritos", "🧺 Mis Listas", "🛒 Compra", "🤖 IA"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("📅 Planificador Semanal")
    planner = ud()["planner"]

    if st.button("🗑️ Limpiar semana", key="clear_planner"):
        ud()["planner"] = {d: [] for d in DIAS}
        save_ud(); st.rerun()

    with st.expander("➕ Añadir receta", expanded=True):
        pa, pb, pc = st.columns([3, 2, 2])
        with pa:
            sp = st.text_input("Buscar receta", placeholder="paella, pollo…", key="plan_srch")
        with pb:
            pday  = st.selectbox("Día",    DIAS,       key="plan_day")
        with pc:
            pmeal = st.selectbox("Turno",  MEAL_SLOTS, key="plan_meal")
        if sp:
            hits = df[df["titulo"].str.contains(sp, case=False, na=False)].head(8)
            if hits.empty:
                st.caption("Sin resultados.")
            for _, row in hits.iterrows():
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(f"**{row['titulo']}** · {row['categoria']} · {row['tiempo_total']}")
                with c2:
                    if st.button("＋", key=f"pa_{row.name}"):
                        ud()["planner"].setdefault(pday, []).append({
                            "titulo": row["titulo"], "meal": pmeal,
                            "comensales": int(row["comensales"]),
                            "ingredientes": row["ingredientes"],
                        })
                        save_ud(); st.rerun()

    cols7 = st.columns(7)
    for i, dia in enumerate(DIAS):
        with cols7[i]:
            st.markdown(f'<div class="day-header">{dia[:3]}</div>', unsafe_allow_html=True)
            entries = ud()["planner"].get(dia, [])
            if not entries:
                st.markdown('<div class="day-box"><span style="color:#aaa;font-size:0.72rem">Vacío</span></div>',
                            unsafe_allow_html=True)
            else:
                box = "<div class='day-box'>"
                for e in entries:
                    icon = e["meal"].split()[0]
                    box += f'<div class="planned-recipe">{icon} {e["titulo"][:20]}…</div>'
                box += "</div>"
                st.markdown(box, unsafe_allow_html=True)
                for j, e in enumerate(entries):
                    if st.button("✕", key=f"prm_{dia}_{j}", help=e["titulo"]):
                        ud()["planner"][dia].pop(j)
                        save_ud(); st.rerun()

    total_pl = sum(len(v) for v in ud()["planner"].values())
    if total_pl:
        st.caption(f"**{total_pl} recetas** planificadas esta semana")

# ══════════════════════════════════════════════════════════════════════════════
# HELPER — recipe card (shared between Explorar and Favoritos)
# ══════════════════════════════════════════════════════════════════════════════
def recipe_card(row, card_key_prefix: str):
    img_col, txt_col = st.columns([1, 2])
    is_fav = row["titulo"] in ud()["favorites"]
    with img_col:
        if row["imagen_url"]:
            st.image(row["imagen_url"], use_container_width=True)
    with txt_col:
        fav_icon = "⭐" if is_fav else "☆"
        st.markdown(f"**{row['titulo']}** {fav_icon}")
        st.markdown(
            f'<span class="recipe-badge">{row["categoria"]}</span>'
            f'<span class="recipe-badge">⏱ {row["tiempo_total"]}</span>'
            f'<span class="recipe-badge">{row["dificultad"].replace("Dificultad ","")}</span>',
            unsafe_allow_html=True,
        )
        if row["valoracion_media"] > 0:
            st.markdown(
                f'<span class="stars">{stars(row["valoracion_media"])}</span> '
                f'<span style="font-size:0.72rem;color:#666">{row["valoracion_media"]:.1f}</span>',
                unsafe_allow_html=True,
            )
        if row["calorias"] > 0:
            st.caption(f"🔥 {row['calorias']:.0f} kcal · 👥 {row['comensales']} pers.")

    with st.expander("Ingredientes, pasos y acciones"):
        # Favorite toggle
        fa, fb = st.columns(2)
        with fa:
            if is_fav:
                if st.button("★ Quitar de favoritos", key=f"{card_key_prefix}_unfav_{row.name}"):
                    ud()["favorites"].remove(row["titulo"])
                    save_ud(); st.rerun()
            else:
                if st.button("☆ Añadir a favoritos", key=f"{card_key_prefix}_fav_{row.name}"):
                    if row["titulo"] not in ud()["favorites"]:
                        ud()["favorites"].append(row["titulo"])
                    save_ud(); st.rerun()

        ings = parse_display(row["ingredientes"])
        if ings:
            st.markdown("**Ingredientes:**")
            for ing in ings:
                st.markdown(f"- {ing}")
        if pd.notna(row.get("pasos")) and row["pasos"]:
            st.markdown("**Preparación:**")
            steps = str(row["pasos"]).split(" | ")
            for s in steps[:5]:
                if s.strip(): st.markdown(s.strip())
            if len(steps) > 5:
                st.caption(f"… y {len(steps)-5} pasos más")
        if row.get("url"):
            st.markdown(f"[Ver receta completa →]({row['url']})")

        st.markdown("**Añadir al planner:**")
        qd, qm, qb = st.columns([2, 2, 1])
        with qd: qday  = st.selectbox("", DIAS,       key=f"{card_key_prefix}_qd_{row.name}")
        with qm: qmeal = st.selectbox("", MEAL_SLOTS, key=f"{card_key_prefix}_qm_{row.name}")
        with qb:
            if st.button("➕", key=f"{card_key_prefix}_qa_{row.name}"):
                ud()["planner"].setdefault(qday, []).append({
                    "titulo": row["titulo"], "meal": qmeal,
                    "comensales": int(row["comensales"]),
                    "ingredientes": row["ingredientes"],
                })
                save_ud(); st.success("✓ Añadida al planner")


def show_recipe_grid(subset: pd.DataFrame, key_prefix: str):
    """Display a paginated 2-col grid of recipe cards."""
    if subset.empty:
        st.info("No hay recetas con esos filtros.")
        return

    sort_key = f"{key_prefix}_sort"
    page_key = f"{key_prefix}_page"
    sort_col = st.selectbox(
        "Ordenar por", ["Valoración ↓", "Tiempo ↑", "Nombre A-Z", "Calorías ↑"], key=sort_key
    )
    s = subset.copy()
    if sort_col == "Valoración ↓":
        s = s.sort_values("valoracion_media", ascending=False)
    elif sort_col == "Tiempo ↑":
        s["_m"] = s["tiempo_total"].apply(time_to_min)
        s = s.sort_values("_m")
    elif sort_col == "Nombre A-Z":
        s = s.sort_values("titulo")
    elif sort_col == "Calorías ↑":
        s = s.sort_values("calorias")

    PAGE = 12
    total_pages = max(1, (len(s) - 1) // PAGE + 1)
    if page_key not in st.session_state:
        st.session_state[page_key] = 1
    page = min(st.session_state[page_key], total_pages)
    page_df = s.iloc[(page - 1) * PAGE: page * PAGE]

    cols2 = st.columns(2)
    for idx, (_, row) in enumerate(page_df.iterrows()):
        with cols2[idx % 2]:
            recipe_card(row, key_prefix)
            st.markdown("---")

    p1, p2, p3 = st.columns([1, 3, 1])
    with p1:
        if st.button("◀", key=f"{key_prefix}_prev") and page > 1:
            st.session_state[page_key] = page - 1; st.rerun()
    with p2:
        st.caption(f"Página {page} de {total_pages} · {len(s):,} recetas")
    with p3:
        if st.button("▶", key=f"{key_prefix}_next") and page < total_pages:
            st.session_state[page_key] = page + 1; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EXPLORAR
# ══════════════════════════════════════════════════════════════════════════════

def expand_by_text(text: str, canon_list: list) -> list:
    """
    Dado un texto libre (ej: "aceite"), devuelve todos los ingredientes canónicos
    que contienen esa palabra. Útil para seleccionar de golpe "aceite de oliva",
    "aceite de girasol", etc.
    """
    t = text.strip().lower()
    if not t:
        return []
    return [c for c in canon_list if t in c]


with tab2:
    st.subheader("🔍 Explorar Recetas")

    with st.expander("🎛️ Filtros", expanded=True):

        # ── Fila 1: nombre, categorías (multi), dificultad (multi) ─────────────
        r1a, r1b, r1c = st.columns([2, 3, 2])
        with r1a:
            search_text = st.text_input("🔎 Nombre receta", placeholder="paella, tortilla…",
                                        key="exp_name")
        with r1b:
            cats_inc = st.multiselect(
                "📂 Categorías",
                sorted(df["categoria"].unique()),
                placeholder="Todas — escribe para filtrar",
                key="exp_cats",
            )
        with r1c:
            difs_inc = st.multiselect(
                "💪 Dificultad",
                sorted(df["dificultad"].unique()),
                placeholder="Todas",
                key="exp_difs",
            )

        # ── Fila 2: ingredientes QUIERO ────────────────────────────────────────
        st.markdown("**✅ Ingredientes que QUIERO**")
        ri2a, ri2b, ri2c = st.columns([3, 2, 2])
        with ri2a:
            # Text search that expands to matching canonical ingredients
            inc_text = st.text_input(
                "Buscar por palabra (selecciona uno o varios del desplegable)",
                placeholder="escribe 'aceite' → aparecen todos los tipos…",
                key="exp_inc_text",
            )
            inc_suggestions = expand_by_text(inc_text, canon_list) if inc_text else canon_list
            ing_inc = st.multiselect(
                "Seleccionar ingredientes",
                options=inc_suggestions,
                placeholder="Escribe arriba para filtrar la lista…",
                key="exp_inc",
            )
        with ri2b:
            # Quick import from a saved list
            my_lists = list(ud().get("ing_lists", {}).keys())
            if my_lists:
                import_inc_list = st.selectbox(
                    "O importar desde Mis Listas",
                    ["— ninguna —"] + my_lists,
                    key="exp_inc_listsel",
                )
                if import_inc_list != "— ninguna —":
                    list_ings = ud()["ing_lists"].get(import_inc_list, [])
                    st.caption(f"{len(list_ings)} ingredientes en «{import_inc_list}»")
            else:
                import_inc_list = "— ninguna —"
                st.caption("(Crea listas en 🧺 Mis Listas)")
        with ri2c:
            logic = st.radio(
                "Lógica incluir",
                ["OR — alguno de estos", "AND — todos estos"],
                horizontal=False,
                key="exp_logic",
            )

        # ── Fila 3: ingredientes NO QUIERO ─────────────────────────────────────
        st.markdown("**🚫 Ingredientes que NO quiero**")
        re3a, re3b, _ = st.columns([3, 2, 2])
        with re3a:
            exc_text = st.text_input(
                "Buscar por palabra",
                placeholder="escribe 'gluten' → aparecen harina, pan…",
                key="exp_exc_text",
            )
            exc_suggestions = expand_by_text(exc_text, canon_list) if exc_text else canon_list
            ing_exc = st.multiselect(
                "Seleccionar ingredientes a excluir",
                options=exc_suggestions,
                placeholder="Escribe arriba para filtrar…",
                key="exp_exc",
            )
        with re3b:
            my_lists = list(ud().get("ing_lists", {}).keys())
            if my_lists:
                import_exc_list = st.selectbox(
                    "O importar desde Mis Listas",
                    ["— ninguna —"] + my_lists,
                    key="exp_exc_listsel",
                )
            else:
                import_exc_list = "— ninguna —"

        # ── Fila 4: tiempo y valoración ────────────────────────────────────────
        r4a, r4b = st.columns(2)
        with r4a:
            max_t = st.select_slider(
                "⏱️ Tiempo máx.",
                [15, 30, 45, 60, 90, 120, 999], value=999,
                format_func=lambda x: "Sin límite" if x == 999 else f"{x} min",
                key="exp_time",
            )
        with r4b:
            min_r = st.slider("⭐ Valoración mín.", 0.0, 5.0, 0.0, 0.5, key="exp_rat")

    # ── Resolver set final de ingredientes (manual + lista importada) ──────────
    ing_lists_data = ud().get("ing_lists", {})

    # Includes: union of manually selected + imported list (expanded by text if word)
    inc_final: set = set(ing_inc)
    if import_inc_list != "— ninguna —":
        for raw in ing_lists_data.get(import_inc_list, []):
            # Each item in the list is already a canonical token; expand by substring too
            inc_final.update(expand_by_text(raw, canon_list) or [raw])

    # Excludes: union of manually selected + imported list
    exc_final: set = set(ing_exc)
    if import_exc_list != "— ninguna —":
        for raw in ing_lists_data.get(import_exc_list, []):
            exc_final.update(expand_by_text(raw, canon_list) or [raw])

    # Show resolved badge counts
    if inc_final or exc_final:
        badge_parts = []
        if inc_final:
            badge_parts.append(f"✅ {len(inc_final)} ingredientes incluidos")
        if exc_final:
            badge_parts.append(f"🚫 {len(exc_final)} ingredientes excluidos")
        st.caption(" · ".join(badge_parts))

    # ── Aplicar filtros ────────────────────────────────────────────────────────
    filt = df.copy()
    if search_text:
        filt = filt[filt["titulo"].str.contains(search_text, case=False, na=False)]
    if cats_inc:
        filt = filt[filt["categoria"].isin(cats_inc)]
    if difs_inc:
        filt = filt[filt["dificultad"].isin(difs_inc)]
    if inc_final:
        if "AND" in logic:
            filt = filt[filt["_ctokens"].apply(lambda t: inc_final.issubset(set(t)))]
        else:
            filt = filt[filt["_ctokens"].apply(lambda t: bool(inc_final & set(t)))]
    if exc_final:
        filt = filt[filt["_ctokens"].apply(lambda t: not bool(exc_final & set(t)))]
    if max_t < 999:
        filt = filt[filt["tiempo_total"].apply(time_to_min) <= max_t]
    if min_r > 0:
        filt = filt[filt["valoracion_media"] >= min_r]

    st.caption(f"**{len(filt):,}** recetas encontradas")
    show_recipe_grid(filt, "exp")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FAVORITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("⭐ Favoritos")
    favs = ud()["favorites"]
    if not favs:
        st.info("Aún no tienes recetas favoritas. Ábrelas en Explorar y pulsa ☆ Añadir a favoritos.")
    else:
        fav_df = df[df["titulo"].isin(favs)]
        st.caption(f"{len(fav_df)} recetas guardadas")
        show_recipe_grid(fav_df, "fav")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MIS LISTAS DE INGREDIENTES
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🧺 Mis Listas de Ingredientes")
    st.caption(
        "Crea listas con nombre (Nevera, Bebé, Despensa…). "
        "Desde cada lista puedes buscar recetas que encajen exactamente o con N ingredientes extra."
    )

    ing_lists: dict = ud().get("ing_lists", {})

    # ── Crear nueva lista ──────────────────────────────────────────────────────
    with st.expander("➕ Nueva lista", expanded=not ing_lists):
        lna, lnb = st.columns([3, 1])
        with lna:
            new_list_name = st.text_input("Nombre de la lista", placeholder="Nevera, Bebé, Despensa…",
                                          key="nl_name")
        with lnb:
            st.write(""); st.write("")
            if st.button("Crear lista", type="primary", key="nl_create"):
                nm = new_list_name.strip()
                if nm and nm not in ing_lists:
                    ing_lists[nm] = []
                    ud()["ing_lists"] = ing_lists
                    save_ud(); st.rerun()
                elif nm in ing_lists:
                    st.warning("Ya existe una lista con ese nombre.")
                else:
                    st.warning("Escribe un nombre.")

    if not ing_lists:
        st.stop()

    # ── Mostrar listas ─────────────────────────────────────────────────────────
    for list_name, list_ings in list(ing_lists.items()):
        st.markdown(f'<div class="list-card"><span class="list-title">🧺 {list_name}</span></div>',
                    unsafe_allow_html=True)

        lk = list_name.replace(" ", "_")

        # Edit ingredients
        with st.expander(f"Editar ingredientes de «{list_name}»"):
            # Add ingredient
            ia, ib = st.columns([4, 1])
            with ia:
                new_ing = st.selectbox(
                    "Añadir ingrediente",
                    [i for i in canon_list if i not in list_ings],
                    key=f"li_add_{lk}",
                    placeholder="Escribe para buscar…",
                )
            with ib:
                st.write(""); st.write("")
                if st.button("Añadir", key=f"li_addbtn_{lk}"):
                    if new_ing and new_ing not in list_ings:
                        ing_lists[list_name].append(new_ing)
                        ud()["ing_lists"] = ing_lists
                        save_ud(); st.rerun()

            # Current ingredients with remove buttons
            if list_ings:
                st.markdown("**Ingredientes actuales:**")
                rows = [list_ings[i:i+4] for i in range(0, len(list_ings), 4)]
                for row_chunk in rows:
                    rcols = st.columns(len(row_chunk))
                    for ci, ing in enumerate(row_chunk):
                        with rcols[ci]:
                            if st.button(f"✕ {ing}", key=f"li_rm_{lk}_{ing[:15]}",
                                         use_container_width=True):
                                ing_lists[list_name].remove(ing)
                                ud()["ing_lists"] = ing_lists
                                save_ud(); st.rerun()
            else:
                st.caption("Lista vacía. Añade ingredientes arriba.")

            # Delete list
            st.markdown("---")
            if st.button(f"🗑️ Eliminar lista «{list_name}»", key=f"li_del_{lk}"):
                del ing_lists[list_name]
                ud()["ing_lists"] = ing_lists
                save_ud(); st.rerun()

        # ── Buscar recetas con esta lista ──────────────────────────────────────
        if list_ings:
            st.markdown(f"**Buscar recetas con «{list_name}»**")
            extra_allowed = st.slider(
                "Ingredientes extra permitidos (+N)",
                min_value=0, max_value=10, value=0,
                key=f"li_extra_{lk}",
                help="0 = solo ingredientes de la lista · 5 = hasta 5 ingredientes extra",
                format="+%d",
            )

            list_set = set(list_ings)

            def match_recipe(ctokens: list) -> bool:
                recipe_set = set(ctokens)
                # ingredients in recipe NOT in the list
                extras = recipe_set - list_set
                # must contain at least one list ingredient
                has_any = bool(recipe_set & list_set)
                return has_any and len(extras) <= extra_allowed

            matched = df[df["_ctokens"].apply(match_recipe)]
            st.caption(
                f"{'🎯 Exacto' if extra_allowed == 0 else f'±{extra_allowed} ingrediente(s) extra'} · "
                f"**{len(matched):,} recetas** encontradas"
            )

            if not matched.empty:
                show_recipe_grid(matched, f"li_{lk}")
        else:
            st.caption("Añade ingredientes a la lista para buscar recetas.")

        st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — LISTA DE LA COMPRA
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.subheader("🛒 Lista de la Compra")
    planned_entries = [e for entries in ud()["planner"].values() for e in entries]

    if not planned_entries:
        st.info("Añade recetas al planner para generar la lista de la compra.")
    else:
        st.caption(f"Basado en **{len(planned_entries)} recetas** planificadas")

        raw_c: Counter = Counter()
        for entry in planned_entries:
            for ing in parse_display(entry.get("ingredientes", "")):
                raw_c[ing.lower().strip()] += 1

        shop_exc = st.multiselect(
            "🚫 Ya lo tengo en casa",
            sorted(raw_c.keys()),
            placeholder="Escribe para buscar y excluir…",
            key="shop_exc",
        )
        exc_set = {e.lower() for e in shop_exc}
        active = {k: v for k, v in raw_c.items() if k not in exc_set}

        CAT_KW = {
            "🥩 Carnes y proteínas": ["pollo","ternera","cerdo","carne","pechuga","muslo",
                "bistec","tocino","bacon","jamón","chorizo","salchicha","atún","salmón",
                "merluza","bacalao","gambas","camarones","huevo","pavo"],
            "🥦 Verduras": ["cebolla","tomate","ajo","pimiento","zanahoria","calabacín",
                "patata","lechuga","espinaca","acelga","champiñon","berenjena","puerro",
                "apio","pepino","coliflor","brócoli","aguacate","maíz","judía","guisante"],
            "🍋 Frutas": ["limón","naranja","manzana","plátano","fresa","mango","piña",
                "uva","kiwi","melocotón","pera","ciruela","pomelo"],
            "🥛 Lácteos": ["leche","nata","mantequilla","queso","yogur","crema",
                "mozzarella","parmesano"],
            "🌾 Cereales y legumbres": ["harina","arroz","pasta","macarrón","espagueti",
                "pan","avena","lenteja","garbanzo","frijol","alubia","quinoa"],
            "🫙 Aceites y salsas": ["aceite","vinagre","soja","mayonesa","ketchup",
                "salsa","caldo","vino","mostaza"],
            "🧂 Especias": ["sal","pimienta","orégano","tomillo","romero","laurel",
                "comino","pimentón","curry","canela","perejil","cilantro","albahaca",
                "azafrán","nuez moscada","azúcar"],
        }

        def cat_of(i):
            il = i.lower()
            for c, kws in CAT_KW.items():
                if any(k in il for k in kws): return c
            return "🍬 Otros"

        by_cat: dict = {}
        for ing, cnt in sorted(active.items()):
            by_cat.setdefault(cat_of(ing), []).append((ing, cnt))

        export = ["LISTA DE LA COMPRA","="*30]
        for cat, items in by_cat.items():
            export.append(f"\n{cat}")
            for ing, cnt in items:
                export.append(f"  ☐ {'('+str(cnt)+'x) ' if cnt>1 else ''}{ing}")

        st.download_button("📥 Exportar .txt", "\n".join(export),
                           "lista_compra.txt", "text/plain")

        if "chk" not in st.session_state:
            st.session_state.chk = set()

        total_i = sum(len(v) for v in by_cat.values())
        done_i  = len([i for i in st.session_state.chk if i in active])
        st.progress(done_i / total_i if total_i else 0,
                    text=f"Completado: {done_i}/{total_i}")
        if st.button("↺ Desmarcar todo", key="shop_reset"):
            st.session_state.chk = set(); st.rerun()

        for cat, items in by_cat.items():
            if not items: continue
            st.markdown(f'<div class="shop-cat">{cat}</div>', unsafe_allow_html=True)
            for ing, cnt in items:
                prefix = f"({cnt}x) " if cnt > 1 else ""
                chk = st.checkbox(f"{prefix}{ing}", value=ing in st.session_state.chk,
                                  key=f"chk_{ing[:50]}")
                if chk: st.session_state.chk.add(ing)
                else:   st.session_state.chk.discard(ing)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — IA
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("🤖 Sugerencias con IA")
    st.caption("Powered by **Groq** (gratuito) · Llama 3.3 70B · Busca en tu dataset real")

    try:
        gkey = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        gkey = ""
    api_key = gkey or st.text_input("API Key de Groq", type="password",
                                     help="Gratis en console.groq.com")
    if not api_key:
        st.info("1. Crea cuenta en [console.groq.com](https://console.groq.com)\n"
                "2. Menú → **API Keys** → **Create API Key**\n"
                "3. Pégala arriba\n\n"
                "Para no introducirla cada vez: `.streamlit/secrets.toml` → `GROQ_API_KEY='gsk_...'`")

    mode = st.radio("¿Qué quieres hacer?", [
        "🥬 Tengo estos ingredientes, ¿qué cocino?",
        "📅 Generar menú semanal equilibrado",
        "🔄 Sustituir un ingrediente",
    ])

    if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
        user_input = st.text_area("¿Qué tienes en casa?",
                                  placeholder="pollo, patatas, cebolla…", height=70)
        extra = st.text_input("Restricciones (opcional)", placeholder="sin gluten, vegetariano…")
    elif mode == "📅 Generar menú semanal equilibrado":
        user_input = ""
        extra = st.text_area("Preferencias", placeholder="4 personas, sin pescado…", height=70)
    else:
        user_input = st.text_input("Ingrediente a sustituir", placeholder="nata líquida")
        extra = st.text_input("Contexto", placeholder="carbonara, sin lactosa")

    if st.button("✨ Preguntar a la IA", type="primary", disabled=not api_key):
        def search_ds(kws, max_r=40):
            if not kws: return df.sample(min(max_r, len(df)))
            mask = pd.Series([False]*len(df), index=df.index)
            for kw in kws:
                kw = kw.strip().lower()
                if len(kw) < 2: continue
                mask |= df["_ctokens"].apply(lambda t: any(kw in x for x in t))
                mask |= df["titulo"].str.lower().str.contains(kw, na=False)
            r = df[mask]
            return r.head(max_r) if not r.empty else df.sample(min(max_r, len(df)))

        def to_txt(sub, mx=25):
            return "\n".join(
                f"- {r['titulo']} | {r['categoria']} | {r['tiempo_total']} | "
                f"Ingredientes: {r['ingredientes'][:160]}"
                for _, r in sub.head(mx).iterrows()
            )

        if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
            kws = [w.strip() for w in user_input.replace(",", " ").split() if len(w.strip()) > 2]
            cands = search_ds(kws)
            prompt = (
                "Eres un asistente de cocina. Tu ÚNICA fuente son estas recetas reales. "
                "NO inventes recetas fuera de la lista.\n\n"
                f"RECETAS:\n{to_txt(cands)}\n\n"
                f"Usuario tiene: {user_input}. Restricciones: {extra or 'ninguna'}.\n"
                "Elige las 5 que mejor encajen. Para cada una: nombre exacto, por qué encaja, "
                "qué ingredientes extra necesita, tiempo. Responde en español."
            )
        elif mode == "📅 Generar menú semanal equilibrado":
            muestra = df.groupby("categoria", group_keys=False).apply(
                lambda g: g.sample(min(6, len(g)))).reset_index(drop=True)
            prompt = (
                "Eres nutricionista y chef. SOLO puedes usar estas recetas reales. "
                "NO inventes recetas fuera de la lista.\n\n"
                f"RECETAS:\n{to_txt(muestra, 50)}\n\n"
                f"Preferencias: {extra or 'ninguna'}.\n"
                "Diseña menú lunes-domingo (comida+cena) con nombres exactos. "
                "Nota final sobre equilibrio nutricional. Responde en español."
            )
        else:
            prompt = (
                f"Quiero sustituir '{user_input}' en: {extra or 'una receta'}.\n"
                "Sugiere 3 sustitutos: nombre, proporción, efecto en sabor/textura. Español."
            )

        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            with st.spinner("Consultando IA…"):
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1200, temperature=0.3,
                )
            st.markdown("### 💬 Respuesta")
            st.markdown(resp.choices[0].message.content)
            if mode != "🔄 Sustituir un ingrediente":
                n = len(cands) if "cands" in dir() else len(muestra)
                st.caption(f"🔍 Analizadas {n} recetas reales de tu dataset.")
        except ImportError:
            st.error("`pip install groq`")
        except Exception as e:
            st.error(f"Error Groq: {e}")

    st.caption("Tu API key no se almacena. Para uso frecuente: `.streamlit/secrets.toml`.")
