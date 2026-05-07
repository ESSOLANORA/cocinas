"""
Planificador de Recetas
Multi-usuario · Favoritos · No deseadas · Notas · Valoración personal
Etiquetas · Escalar recetas · Historial · Listas · Filtro exacto/+N · IA Groq
"""
import streamlit as st
import pandas as pd
import re, json, zipfile, io
from pathlib import Path
from collections import Counter
from datetime import date

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG & CONSTANTES
# ══════════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="🍽️ Recetas", page_icon="🍽️",
                   layout="wide", initial_sidebar_state="collapsed")

DATA_DIR   = Path("data")
USERS_FILE = DATA_DIR / "users.json"
DATA_DIR.mkdir(exist_ok=True)

DIAS       = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
MEAL_SLOTS = ["🌅 Desayuno","☀️ Comida","🌙 Cena"]
AVATARS    = ["👤","👨","👩","👦","👧","🧑","👴","👵","🧔","👶",
              "🐱","🐶","🦊","🐻","🐼","🐨","🦁","🐯","🐸","🦄"]
STAR_LABELS = ["","⭐","⭐⭐","⭐⭐⭐","⭐⭐⭐⭐","⭐⭐⭐⭐⭐"]

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""<style>
[data-testid="stAppViewContainer"]{padding-top:.4rem}
.main .block-container{padding:.4rem 1.1rem 2rem;max-width:990px}
[data-testid="stTabs"] button{font-size:.8rem;padding:.3rem .65rem}
.rb{display:inline-block;background:#e8f4fd;color:#1565c0;border-radius:6px;
    padding:2px 7px;font-size:.68rem;margin-right:3px;margin-top:3px}
.rb-tag{background:#fce7f3;color:#9d174d}
.rb-no{background:#fee2e2;color:#991b1b}
.rb-my{background:#dcfce7;color:#166534}
.day-header{background:linear-gradient(135deg,#667eea,#764ba2);color:white;
    padding:.4rem .65rem;border-radius:8px 8px 0 0;font-weight:600;font-size:.83rem}
.day-box{border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px;
    padding:.5rem;min-height:70px;background:white;margin-bottom:.35rem}
.pr{background:#f0fdf4;border:1px solid #86efac;border-radius:5px;
    padding:3px 6px;font-size:.73rem;margin:2px 0;color:#166534}
.lcard{background:#f8f9fa;border:1px solid #dee2e6;border-radius:10px;padding:.75rem;margin-bottom:.5rem}
.shopcat{font-weight:700;color:#7c3aed;margin-top:.7rem;font-size:.86rem}
.stars{color:#f59e0b;font-size:.8rem}
footer{visibility:hidden}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# USER DATA HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def load_users() -> dict:
    return json.loads(USERS_FILE.read_text("utf-8")) if USERS_FILE.exists() else {}

def save_users(u: dict):
    USERS_FILE.write_text(json.dumps(u, ensure_ascii=False, indent=2), "utf-8")

def user_file(name: str) -> Path:
    return DATA_DIR / f"user_{re.sub(r'[^\\w-]','_',name.lower())}.json"

def empty_user() -> dict:
    return {
        "planner":   {d: [] for d in DIAS},
        "history":   [],          # [{"week":"2024-W01","days":{...}}]
        "favorites": [],          # [titulo]
        "hidden":    [],          # [titulo] — recetas no deseadas
        "ratings":   {},          # {titulo: 1-5}
        "notes":     {},          # {titulo: "texto"}
        "tags":      {},          # {titulo: ["#rapida","#bebe"]}
        "ing_lists": {},          # {nombre: [canon_ing]}
        "saved_searches": {},   # {nombre: {filter params}}
    }

def load_user_data(name: str) -> dict:
    f = user_file(name)
    if not f.exists():
        return empty_user()
    data = json.loads(f.read_text("utf-8"))
    # backfill missing keys for old profiles
    base = empty_user()
    for k, v in base.items():
        data.setdefault(k, v)
    return data

def save_user_data(name: str, data: dict):
    user_file(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

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
    r"loncha[s]?)\s+(?:de\s+)?", re.IGNORECASE)

def _clean_token(item: str) -> str:
    item = re.sub(r"^[\d½¼¾/.,\s]+", "", item)
    item = _UNIT_RE.sub("", item)
    item = re.sub(r"^(?:sopera[s]?|postre[s]?)\s+de\s+", "", item, flags=re.IGNORECASE)
    item = re.sub(r"^de\s+", "", item, flags=re.IGNORECASE)
    item = re.sub(r"\s*\(.*?\)", "", item)
    item = re.sub(r"\s+al\s+gusto.*$", "", item)
    return item.strip().lower()

def tokenize(ing_str: str) -> list:
    out = []
    for item in (ing_str or "").split(" | "):
        t = _clean_token(item.strip())
        if len(t) > 2 and not t.startswith("##") and not t.startswith("para"):
            out.append(t)
    return out

def parse_display(ing_str: str) -> list:
    return [i.strip() for i in (ing_str or "").split(" | ")
            if i.strip() and not i.strip().startswith("##")]

def time_to_min(t: str) -> int:
    if not t: return 9999
    m = re.match(r"(?:(\d+)h\s*)?(?:(\d+)m)?", t)
    return (int(m.group(1) or 0)*60 + int(m.group(2) or 0)) if m else 9999

def star_html(r: float) -> str:
    n = int(round(r)); return "★"*n + "☆"*(5-n)

def expand_by_text(text: str, clist: list) -> list:
    t = text.strip().lower()
    return [c for c in clist if t in c] if t else []

# ── Dataset ────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Cargando recetas…")
def load_data(path: str) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    if ext == ".csv":
        for enc in ("utf-8","utf-8-sig","latin-1","cp1252"):
            try: df = pd.read_csv(path, encoding=enc, low_memory=False); break
            except UnicodeDecodeError: continue
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
    df["_tokens"]          = df["ingredientes"].apply(tokenize)
    return df

@st.cache_data(show_spinner="Indexando ingredientes…")
def build_vocab(_df: pd.DataFrame) -> tuple:
    try:
        from rapidfuzz import fuzz, process; fuzzy = True
    except ImportError:
        fuzzy = False
    counter: Counter = Counter()
    for t in _df["_tokens"]: counter.update(t)
    vocab = sorted([k for k,v in counter.items() if v>=3], key=lambda x:-counter[x])
    if not fuzzy:
        return {t:t for t in vocab}, sorted(vocab)
    cmap, assigned = {}, set()
    for term in vocab:
        if term in assigned: continue
        hits = process.extract(term, vocab, scorer=fuzz.token_sort_ratio, limit=12, score_cutoff=83)
        group = [h[0] for h in hits if h[0] not in assigned] or [term]
        canon = max(group, key=lambda x: counter.get(x,0))
        for v in group: cmap[v] = canon
        assigned.update(group)
    return cmap, sorted(set(cmap.values()))

@st.cache_data(show_spinner=False)
def canonical_tokens(_df: pd.DataFrame, _cmap: dict) -> pd.Series:
    return _df["_tokens"].apply(lambda toks: list({_cmap.get(t,t) for t in toks}))

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR — dataset + backup
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Dataset")
    uploaded = st.file_uploader("Cargar dataset", type=["xlsx","csv"])
    dataset_path = None
    if uploaded:
        ext = Path(uploaded.name).suffix.lower()
        sname = f"dataset{ext}"
        Path(sname).write_bytes(uploaded.read())
        dataset_path = sname
        st.success(f"✓ {uploaded.name}")
    st.caption("O coloca `dataset.csv` / `dataset.xlsx` junto a `app.py`.")

    st.markdown("---")
    st.markdown("**💾 Datos persistentes**")

    # ── GitHub sync (auto-persists across deploys) ─────────────────────────
    try:
        gh_token = st.secrets.get("GITHUB_TOKEN", "")
        gh_repo  = st.secrets.get("GITHUB_REPO", "")   # "usuario/repo"
        gh_branch= st.secrets.get("GITHUB_BRANCH", "main")
    except Exception:
        gh_token = gh_repo = gh_branch = ""

    def gh_save_all():
        """Push all data JSONs to GitHub data/ folder."""
        if not gh_token or not gh_repo:
            return False
        import base64, urllib.request, urllib.error
        files_to_push = []
        if USERS_FILE.exists():
            files_to_push.append(("data/users.json", USERS_FILE.read_bytes()))
        for f in DATA_DIR.glob("user_*.json"):
            files_to_push.append((f"data/{f.name}", f.read_bytes()))

        headers = {"Authorization": f"token {gh_token}",
                   "Content-Type": "application/json"}
        api = f"https://api.github.com/repos/{gh_repo}/contents/"

        for path, content in files_to_push:
            # Get current SHA if file exists (needed for update)
            sha = None
            try:
                req = urllib.request.Request(api + path, headers=headers)
                with urllib.request.urlopen(req) as r:
                    sha = json.loads(r.read())["sha"]
            except urllib.error.HTTPError:
                pass  # file doesn't exist yet, that's fine

            payload = json.dumps({
                "message": "recetas: sync data",
                "content": base64.b64encode(content).decode(),
                "branch": gh_branch,
                **({"sha": sha} if sha else {})
            }).encode()
            try:
                req = urllib.request.Request(api + path, data=payload,
                                             headers=headers, method="PUT")
                urllib.request.urlopen(req)
            except Exception:
                return False
        return True

    def gh_load_all():
        """Pull all data JSONs from GitHub data/ folder."""
        if not gh_token or not gh_repo:
            return False
        import base64, urllib.request, urllib.error
        headers = {"Authorization": f"token {gh_token}"}
        api = f"https://api.github.com/repos/{gh_repo}/contents/data?ref={gh_branch}"
        try:
            req = urllib.request.Request(api, headers=headers)
            with urllib.request.urlopen(req) as r:
                files = json.loads(r.read())
        except Exception:
            return False

        DATA_DIR.mkdir(exist_ok=True)
        for entry in files:
            if not entry["name"].endswith(".json"): continue
            try:
                req = urllib.request.Request(entry["download_url"], headers=headers)
                with urllib.request.urlopen(req) as r:
                    (DATA_DIR / entry["name"]).write_bytes(r.read())
            except Exception:
                continue
        return True

    if gh_token and gh_repo:
        st.caption(f"🔗 Sincronización GitHub activa · `{gh_repo}`")
        gc1, gc2 = st.columns(2)
        with gc1:
            if st.button("☁️ Guardar en GitHub", use_container_width=True):
                with st.spinner("Guardando…"):
                    ok = gh_save_all()
                st.success("✓ Guardado en GitHub") if ok else st.error("Error al guardar")
        with gc2:
            if st.button("⬇️ Cargar desde GitHub", use_container_width=True):
                with st.spinner("Cargando…"):
                    ok = gh_load_all()
                if ok:
                    for k in ("current_user","user_data"): st.session_state.pop(k,None)
                    st.success("✓ Datos cargados"); st.rerun()
                else:
                    st.error("Error al cargar")
        # Auto-load on first run if data dir is empty
        if not any(DATA_DIR.glob("*.json")):
            with st.spinner("Recuperando datos de GitHub…"):
                if gh_load_all():
                    for k in ("current_user","user_data"): st.session_state.pop(k,None)
                    st.rerun()
    else:
        st.caption("Configura GitHub en secrets.toml para persistencia automática. "
                   "O usa el backup manual:")

    # ── Manual ZIP backup (always available) ──────────────────────────────
    with st.expander("📦 Backup manual (ZIP)"):
        if st.button("📤 Exportar", use_container_width=True):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                if USERS_FILE.exists(): zf.write(USERS_FILE, "users.json")
                for f in DATA_DIR.glob("user_*.json"): zf.write(f, f.name)
            buf.seek(0)
            st.download_button("⬇️ Descargar backup.zip", buf.getvalue(),
                               "recetas_backup.zip", "application/zip",
                               use_container_width=True)
        rzip = st.file_uploader("📥 Restaurar", type=["zip"], key="restore_zip")
        if rzip:
            with zipfile.ZipFile(io.BytesIO(rzip.read())) as zf:
                for name in zf.namelist():
                    (DATA_DIR / name).write_bytes(zf.read(name))
            for k in ("current_user","user_data"): st.session_state.pop(k,None)
            st.success("✓ Restaurado"); st.rerun()

if not dataset_path:
    for c in ["dataset.csv","dataset.xlsx"]:
        if Path(c).exists(): dataset_path = c; break

# ══════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════
st.title("🍽️ Planificador de Recetas")
if not dataset_path:
    st.info("👆 Sube tu dataset desde el menú lateral."); st.stop()

try:
    df = load_data(dataset_path)
except Exception as e:
    st.error(f"Error: {e}"); st.stop()

cmap, canon_list = build_vocab(df)
df["_ct"] = canonical_tokens(df, cmap)

# ══════════════════════════════════════════════════════════════════════════════
# PROFILE SELECTOR
# ══════════════════════════════════════════════════════════════════════════════
users = load_users()
hc1, hc2, hc3 = st.columns([3, 2, 2])
with hc2:
    user_names = list(users.keys())
    sel = st.selectbox("👤 Perfil", user_names + ["＋ Nuevo perfil"],
                       index=user_names.index(st.session_state.get("current_user","__none__"))
                             if st.session_state.get("current_user") in user_names else 0,
                       label_visibility="collapsed")
with hc3:
    if sel != "＋ Nuevo perfil" and sel in users:
        av = users[sel].get("avatar","👤")
        st.markdown(f'<div style="background:#f0f4ff;border-radius:8px;padding:.4rem .8rem;'
                    f'display:flex;align-items:center;gap:8px">'
                    f'<span style="font-size:1.5rem">{av}</span>'
                    f'<b>{sel}</b></div>', unsafe_allow_html=True)
        if st.button("🗑️ Eliminar perfil", key="del_user"):
            st.session_state["confirm_delete"] = sel

# Confirm delete
if st.session_state.get("confirm_delete") in users:
    todel = st.session_state["confirm_delete"]
    st.warning(f"⚠️ ¿Eliminar **{todel}** y todos sus datos? No se puede deshacer.")
    cd1, cd2, _ = st.columns([1,1,5])
    with cd1:
        if st.button("Sí, eliminar", type="primary"):
            del users[todel]; save_users(users)
            f = user_file(todel)
            if f.exists(): f.unlink()
            for k in ("confirm_delete","current_user","user_data"): st.session_state.pop(k,None)
            st.rerun()
    with cd2:
        if st.button("Cancelar"):
            st.session_state.pop("confirm_delete",None); st.rerun()

# New profile form
if sel == "＋ Nuevo perfil":
    st.markdown("### Crear perfil")
    na, nb, nc = st.columns([3,2,1])
    with na: new_name = st.text_input("Nombre", placeholder="Tu nombre…")
    with nb: new_av   = st.selectbox("Avatar", AVATARS)
    with nc:
        st.write(""); st.write("")
        if st.button("Crear", type="primary"):
            nn = new_name.strip()
            if nn:
                users[nn] = {"avatar": new_av}; save_users(users)
                st.session_state.current_user = nn
                st.session_state.user_data    = load_user_data(nn)
                st.rerun()
            else: st.warning("Escribe un nombre.")
    st.stop()

if not users:
    st.info("Crea tu primer perfil con el desplegable."); st.stop()

if st.session_state.get("current_user") != sel:
    st.session_state.current_user = sel
    st.session_state.user_data    = load_user_data(sel)
if "user_data" not in st.session_state:
    st.session_state.user_data = load_user_data(sel)

st.caption(f"📊 {len(df):,} recetas · {df['categoria'].nunique()} categorías · "
           f"{len(canon_list):,} ingredientes · Perfil: **{users[sel].get('avatar','👤')} {sel}**")

# ══════════════════════════════════════════════════════════════════════════════
# RECIPE CARD HELPER
# ══════════════════════════════════════════════════════════════════════════════
def recipe_card(row, kp: str):
    titulo  = row["titulo"]
    is_fav  = titulo in ud()["favorites"]
    is_hide = titulo in ud()["hidden"]
    my_rat  = ud()["ratings"].get(titulo, 0)
    my_note = ud()["notes"].get(titulo, "")
    my_tags = ud()["tags"].get(titulo, [])
    base_com = int(row["comensales"]) or 1

    ic, tc = st.columns([1,2])
    with ic:
        if row["imagen_url"]: st.image(row["imagen_url"], use_container_width=True)
    with tc:
        fav_icon = "⭐" if is_fav else "☆"
        st.markdown(f"**{titulo}** {fav_icon}")
        badges = (f'<span class="rb">{row["categoria"]}</span>'
                  f'<span class="rb">⏱ {row["tiempo_total"]}</span>'
                  f'<span class="rb">{row["dificultad"].replace("Dificultad ","")}</span>')
        if my_tags:
            for tag in my_tags:
                badges += f'<span class="rb rb-tag">{tag}</span>'
        st.markdown(badges, unsafe_allow_html=True)
        if row["valoracion_media"] > 0:
            st.markdown(f'<span class="stars">{star_html(row["valoracion_media"])}</span> '
                        f'<span style="font-size:.7rem;color:#666">{row["valoracion_media"]:.1f} (dataset)</span>',
                        unsafe_allow_html=True)
        if my_rat:
            st.markdown(f'<span class="rb rb-my">Mi valoración: {"⭐"*my_rat}</span>',
                        unsafe_allow_html=True)
        if row["calorias"] > 0:
            st.caption(f"🔥 {row['calorias']:.0f} kcal · 👥 {base_com} pers.")

    with st.expander("Detalle, valorar, anotar, etiquetar"):
        # ── Acciones rápidas ────────────────────────────────────────────────
        a1, a2, a3 = st.columns(3)
        with a1:
            if is_fav:
                if st.button("★ Quitar fav", key=f"{kp}_uf_{row.name}"):
                    ud()["favorites"].remove(titulo); save_ud(); st.rerun()
            else:
                if st.button("☆ Favorito", key=f"{kp}_f_{row.name}"):
                    ud()["favorites"].append(titulo); save_ud(); st.rerun()
        with a2:
            if is_hide:
                if st.button("👁 Mostrar", key=f"{kp}_uh_{row.name}"):
                    ud()["hidden"].remove(titulo); save_ud(); st.rerun()
            else:
                if st.button("🚫 No mostrar", key=f"{kp}_h_{row.name}"):
                    ud()["hidden"].append(titulo); save_ud(); st.rerun()
        with a3:
            # Planner — next free slot (one click) or manual pick
            nfd, nfm = next_free_slot(ud()["planner"])
            nf_label = f"⏭️ → {nfd[:3]}/{nfm.split()[0]}" if nfd != "_reserva" else "⏭️ Reserva"
            if st.button(nf_label, key=f"{kp}_qnext_{row.name}",
                         help="Añadir al siguiente hueco libre",
                         use_container_width=True):
                add_to_planner(row, nfd, nfm)
                st.success(f"✓ {nfd} / {nfm.split(None,1)[-1] if nfd != '_reserva' else nfm}")
            with st.expander("Elegir día/turno"):
                qday  = st.selectbox("", DIAS,       key=f"{kp}_qd_{row.name}")
                qmeal = st.selectbox("", MEAL_SLOTS, key=f"{kp}_qm_{row.name}")
                if st.button("➕", key=f"{kp}_qa_{row.name}"):
                    add_to_planner(row, qday, qmeal)
                    st.success("✓")

        # ── Mi valoración ───────────────────────────────────────────────────
        new_rat = st.select_slider("Mi valoración",
                                   options=[0,1,2,3,4,5],
                                   value=my_rat,
                                   format_func=lambda x: STAR_LABELS[x] if x else "Sin valorar",
                                   key=f"{kp}_rat_{row.name}")
        if new_rat != my_rat:
            ud()["ratings"][titulo] = new_rat; save_ud(); st.rerun()

        # ── Etiquetas ────────────────────────────────────────────────────────
        st.markdown("**Etiquetas personales**")
        all_existing_tags = sorted({t for tags in ud()["tags"].values() for t in tags})
        te1, te2 = st.columns([3,1])
        with te1:
            new_tag = st.text_input("Nueva etiqueta", placeholder="#rapida, #bebe, #domingo…",
                                    key=f"{kp}_tagi_{row.name}")
        with te2:
            st.write("")
            if st.button("Añadir", key=f"{kp}_tagbtn_{row.name}") and new_tag.strip():
                tag = new_tag.strip()
                if not tag.startswith("#"): tag = "#" + tag
                tags_r = ud()["tags"].setdefault(titulo, [])
                if tag not in tags_r: tags_r.append(tag)
                save_ud(); st.rerun()
        if my_tags:
            for tag in my_tags:
                if st.button(f"✕ {tag}", key=f"{kp}_rmtag_{row.name}_{tag}"):
                    ud()["tags"][titulo].remove(tag); save_ud(); st.rerun()

        # ── Nota personal ────────────────────────────────────────────────────
        new_note = st.text_area("📝 Mi nota", value=my_note,
                                placeholder="Sin picante, doblar el ajo, usar leche de avena…",
                                key=f"{kp}_note_{row.name}", height=70)
        if new_note != my_note:
            ud()["notes"][titulo] = new_note; save_ud()

        # ── Escalar recetas ──────────────────────────────────────────────────
        ings = parse_display(row["ingredientes"])
        if ings:
            st.markdown("**Ingredientes** (escalar por comensales)")
            scale = st.number_input("Comensales", min_value=1, max_value=20,
                                    value=base_com, key=f"{kp}_sc_{row.name}")
            factor = scale / base_com if base_com else 1
            _num_re = re.compile(r"^([\d½¼¾.,/]+)\s*(.*)")

            def scale_ing(s: str, f: float) -> str:
                m = _num_re.match(s)
                if not m: return s
                try:
                    raw = m.group(1).replace(",",".")
                    n = eval(raw.replace("½",".5").replace("¼",".25").replace("¾",".75"))
                    scaled = n * f
                    fmt = f"{scaled:.0f}" if scaled == int(scaled) else f"{scaled:.1f}"
                    return f"{fmt} {m.group(2)}"
                except Exception:
                    return s

            for ing in ings:
                st.markdown(f"- {scale_ing(ing, factor)}")

        if pd.notna(row.get("pasos")) and row["pasos"]:
            st.markdown("**Preparación:**")
            steps = str(row["pasos"]).split(" | ")
            for s in steps[:6]:
                if s.strip(): st.markdown(s.strip())
            if len(steps) > 6: st.caption(f"… y {len(steps)-6} pasos más")
        if row.get("url"):
            st.markdown(f"[Ver receta completa →]({row['url']})")


def recipe_grid(subset: pd.DataFrame, kp: str, hide_hidden: bool = True):
    if hide_hidden:
        hidden_set = set(ud().get("hidden", []))
        subset = subset[~subset["titulo"].isin(hidden_set)]
    if subset.empty:
        st.info("No hay recetas con esos filtros."); return

    skey  = f"{kp}_sort"
    pgkey = f"{kp}_pg"
    sc = st.selectbox("Ordenar", ["Valoración ↓","Mi valoración ↓","Tiempo ↑","Nombre A-Z","Calorías ↑"], key=skey)
    s = subset.copy()
    if sc == "Valoración ↓":      s = s.sort_values("valoracion_media", ascending=False)
    elif sc == "Mi valoración ↓":
        s["_mr"] = s["titulo"].map(lambda t: ud()["ratings"].get(t,0))
        s = s.sort_values("_mr", ascending=False)
    elif sc == "Tiempo ↑":
        s["_m"] = s["tiempo_total"].apply(time_to_min); s = s.sort_values("_m")
    elif sc == "Nombre A-Z":      s = s.sort_values("titulo")
    elif sc == "Calorías ↑":      s = s.sort_values("calorias")

    PAGE = 12
    total_pg = max(1,(len(s)-1)//PAGE+1)
    if pgkey not in st.session_state: st.session_state[pgkey] = 1
    pg = min(st.session_state[pgkey], total_pg)
    page_df = s.iloc[(pg-1)*PAGE: pg*PAGE]

    cols2 = st.columns(2)
    for idx, (_, row) in enumerate(page_df.iterrows()):
        with cols2[idx%2]:
            recipe_card(row, kp); st.markdown("---")

    p1,p2,p3 = st.columns([1,3,1])
    with p1:
        if st.button("◀", key=f"{kp}_prev") and pg > 1:
            st.session_state[pgkey] = pg-1; st.rerun()
    with p2: st.caption(f"Pág. {pg}/{total_pg} · {len(s):,} recetas")
    with p3:
        if st.button("▶", key=f"{kp}_next") and pg < total_pg:
            st.session_state[pgkey] = pg+1; st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8 = st.tabs(
    ["📅 Planner","🔍 Explorar","🍽️ Generar Menú","⭐ Favoritos","🧺 Mis Listas","🛒 Compra","📖 Historial","🤖 IA"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLANNER
# ══════════════════════════════════════════════════════════════════════════════

def planner_occupied(planner: dict) -> set:
    """Return set of (dia, meal) tuples already occupied."""
    occ = set()
    for dia, entries in planner.items():
        for e in entries:
            occ.add((dia, e["meal"]))
    return occ

def next_free_slot(planner: dict) -> tuple:
    """
    Returns (dia, meal) of the next free slot in week order.
    If week is full, returns a 'reserve' label.
    """
    occ = planner_occupied(planner)
    for dia in DIAS:
        for meal in MEAL_SLOTS:
            if (dia, meal) not in occ:
                return dia, meal
    # Week full — count existing reserves
    reserves = planner.get("_reservas", [])
    return "_reserva", f"Reserva #{len(reserves)+1}"

def add_to_planner(row, dia: str, meal: str):
    entry = {
        "titulo": row["titulo"], "meal": meal,
        "comensales": int(row["comensales"]),
        "ingredientes": row["ingredientes"],
    }
    if dia == "_reserva":
        ud()["planner"].setdefault("_reservas", []).append(entry)
    else:
        ud()["planner"].setdefault(dia, []).append(entry)
    save_ud()


with tab1:
    st.subheader("📅 Planificador Semanal")
    pc1, pc2, pc3 = st.columns([1,2,3])
    with pc1:
        if st.button("🗑️ Limpiar"):
            ud()["planner"] = {d:[] for d in DIAS}; save_ud(); st.rerun()
    with pc2:
        if st.button("📖 Guardar en historial"):
            week_label = date.today().strftime("Semana %Y-W%V (%d/%m/%Y)")
            ud()["history"].append({"week": week_label, "days": {d: ud()["planner"].get(d,[]) for d in DIAS}})
            save_ud(); st.success(f"✓ «{week_label}»")
    with pc3:
        # Show next free slot info
        ndia, nmeal = next_free_slot(ud()["planner"])
        if ndia == "_reserva":
            st.caption(f"📋 Semana completa · el siguiente irá a {nmeal}")
        else:
            st.caption(f"⏭️ Siguiente hueco libre: **{ndia}** / **{nmeal}**")

    with st.expander("➕ Añadir receta", expanded=True):
        pa, pb, pc4, pd_col = st.columns([3,2,2,2])
        with pa: sp = st.text_input("Buscar", placeholder="pollo, paella…", key="pl_srch")
        with pb:
            occ = planner_occupied(ud()["planner"])
            # Only show free days (or all if all full)
            free_days = [d for d in DIAS if any((d,m) not in occ for m in MEAL_SLOTS)]
            pday = st.selectbox("Día", free_days if free_days else DIAS, key="pl_day")
        with pc4:
            free_meals = [m for m in MEAL_SLOTS if (pday, m) not in occ]
            pmeal = st.selectbox("Turno", free_meals if free_meals else MEAL_SLOTS, key="pl_meal",
                                 help="Solo muestra huecos libres" if free_meals else "Todos ocupados → irá a Reservas")
        with pd_col:
            add_next = st.checkbox("⏭️ Añadir al siguiente hueco libre", value=True, key="pl_next")

        if sp:
            hits = df[df["titulo"].str.contains(sp, case=False, na=False)].head(8)
            if hits.empty: st.caption("Sin resultados.")
            for _, row in hits.iterrows():
                c1, c2 = st.columns([5,1])
                with c1:
                    st.markdown(f"**{row['titulo']}** · {row['categoria']} · {row['tiempo_total']}")
                with c2:
                    if st.button("＋", key=f"pladd_{row.name}"):
                        if add_next:
                            td, tm = next_free_slot(ud()["planner"])
                        else:
                            td, tm = pday, pmeal
                        add_to_planner(row, td, tm)
                        st.rerun()

    # ── Weekly grid ───────────────────────────────────────────────────────────
    cols7 = st.columns(7)
    for i, dia in enumerate(DIAS):
        with cols7[i]:
            st.markdown(f'<div class="day-header">{dia[:3]}</div>', unsafe_allow_html=True)
            entries = ud()["planner"].get(dia, [])
            occ_meals = {e["meal"] for e in entries}
            if not entries:
                st.markdown('<div class="day-box"><span style="color:#aaa;font-size:.7rem">Vacío</span></div>',
                            unsafe_allow_html=True)
            else:
                box = "<div class='day-box'>"
                for e in entries:
                    box += f'<div class="pr">{e["meal"].split()[0]} {e["titulo"][:16]}…</div>'
                # Show locked meals
                for meal in MEAL_SLOTS:
                    if meal not in occ_meals:
                        icon = meal.split()[0]
                        box += f'<div style="color:#ccc;font-size:.65rem">{icon} libre</div>'
                box += "</div>"
                st.markdown(box, unsafe_allow_html=True)
                for j, e in enumerate(entries):
                    if st.button("✕", key=f"prm_{dia}_{j}", help=e["titulo"]):
                        ud()["planner"][dia].pop(j); save_ud(); st.rerun()

    # ── Reservas (overflow) ───────────────────────────────────────────────────
    reservas = ud()["planner"].get("_reservas", [])
    if reservas:
        st.markdown("**📋 Reservas** (semana completa al añadir)")
        for j, e in enumerate(reservas):
            rc1, rc2, rc3 = st.columns([4,2,1])
            with rc1: st.markdown(f"**{e['titulo']}**")
            with rc2:
                # Move to a specific slot
                free_slots = [(d,m) for d in DIAS for m in MEAL_SLOTS
                              if (d,m) not in planner_occupied(ud()["planner"])]
                if free_slots:
                    slot_labels = [f"{d} / {m.split()[1]}" for d,m in free_slots]
                    chosen = st.selectbox("Mover a", slot_labels, key=f"res_move_{j}")
                    if st.button("Mover", key=f"res_movebtn_{j}"):
                        td, tm = free_slots[slot_labels.index(chosen)]
                        ud()["planner"].setdefault(td,[]).append(e)
                        ud()["planner"]["_reservas"].pop(j)
                        save_ud(); st.rerun()
            with rc3:
                if st.button("✕", key=f"res_rm_{j}"):
                    ud()["planner"]["_reservas"].pop(j); save_ud(); st.rerun()

    total_pl = sum(len(v) for d,v in ud()["planner"].items() if d != "_reservas")
    st.caption(f"**{total_pl} recetas** · {len(reservas)} en reserva")

    # ── Explorar recetas del planner ──────────────────────────────────────────
    if total_pl > 0:
        with st.expander(f"🔍 Ver todas las recetas del planner ({total_pl})", expanded=False):
            planned_titles = {e["titulo"]
                              for d,v in ud()["planner"].items() if d != "_reservas"
                              for e in v}
            planned_df = df[df["titulo"].isin(planned_titles)]
            if not planned_df.empty:
                recipe_grid(planned_df, "pl_view", hide_hidden=False)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EXPLORAR
# ══════════════════════════════════════════════════════════════════════════════

# ── Pre-compute caracteristicas vocabulary ────────────────────────────────────
@st.cache_data(show_spinner=False)
def build_char_vocab(_df: pd.DataFrame) -> list:
    c: Counter = Counter()
    for val in _df.get("caracteristicas", pd.Series(dtype=str)).dropna():
        for ch in val.split(","):
            ch = ch.strip()
            if ch: c[ch] += 1
    return sorted([k for k,v in c.items() if v >= 2])

@st.cache_data(show_spinner=False)
def char_token_col(_df: pd.DataFrame) -> pd.Series:
    def parse(val):
        if not val or not isinstance(val, str): return []
        return [c.strip() for c in val.split(",") if c.strip()]
    return _df.get("caracteristicas", pd.Series([""] * len(_df))).apply(parse)

char_vocab = build_char_vocab(df)
df["_chars"] = char_token_col(df)

# ── Accumulating selector ─────────────────────────────────────────────────────
def acc_selector(label: str, vocab_with_counts: list, acc_key: str,
                 txt_key: str, sel_key: str, list_key: str,
                 logic_key: str = None,
                 chip_color: str = "#e8f4fd", chip_text: str = "#1565c0") -> tuple:
    """
    vocab_with_counts: list of "Value (42)" strings for display,
                       or plain strings if no counts.
    Returns (final_set of plain values, logic_str)
    """
    if acc_key not in st.session_state:
        st.session_state[acc_key] = []
    acc: list = st.session_state[acc_key]

    # Strip counts for matching
    def plain(s):
        import re
        return re.sub(r"\s*\(\d+\)$", "", s).strip()

    st.markdown(f"**{label}**")
    col_search, col_import = st.columns([3, 2])

    with col_search:
        txt = st.text_input("Buscar", placeholder="escribe para filtrar…",
                            key=txt_key, label_visibility="collapsed")
        plain_acc = set(acc)
        if txt:
            tl = txt.strip().lower()
            suggestions = [v for v in vocab_with_counts
                           if tl in plain(v).lower() and plain(v) not in plain_acc]
        else:
            suggestions = [v for v in vocab_with_counts if plain(v) not in plain_acc]

        new_sel = st.multiselect("Añadir", options=suggestions,
                                 placeholder="Selecciona uno o varios…",
                                 key=sel_key, label_visibility="collapsed")
        if new_sel:
            for item in new_sel:
                pv = plain(item)
                if pv not in acc: acc.append(pv)
            st.session_state[acc_key] = acc
            st.rerun()

    with col_import:
        my_lists = list(ud().get("ing_lists", {}).keys())
        imp = st.selectbox("De lista", ["—"] + my_lists, key=list_key,
                           label_visibility="collapsed")
        if imp != "—":
            st.caption(f"📋 {imp}")
            if st.button("Importar", key=f"imp_{list_key}"):
                # vocab_with_counts may or may not be canon_list
                plain_vocab = [plain(v) for v in vocab_with_counts]
                for raw in ud()["ing_lists"].get(imp, []):
                    expanded = expand_by_text(raw, plain_vocab) or [raw]
                    for e in expanded:
                        if e not in acc: acc.append(e)
                st.session_state[acc_key] = acc
                st.rerun()

    if acc:
        chips_html = " ".join(
            f'<span style="display:inline-block;background:{chip_color};color:{chip_text};'
            f'border-radius:14px;padding:3px 10px;font-size:.75rem;margin:2px 2px 2px 0">'
            f'{i}</span>' for i in acc
        )
        st.markdown(chips_html + f'<span style="font-size:.7rem;color:#888"> · {len(acc)}</span>',
                    unsafe_allow_html=True)
        if st.button("✕ Limpiar todo", key=f"clr_{acc_key}"):
            st.session_state[acc_key] = []; st.rerun()

    logic = "OR — alguno"
    if logic_key:
        logic = st.radio("Lógica", ["OR — alguno", "AND — todos"],
                         horizontal=True, key=logic_key)

    final: set = set(acc)
    if imp != "—":
        plain_vocab = [plain(v) for v in vocab_with_counts]
        for raw in ud()["ing_lists"].get(imp, []):
            final.update(expand_by_text(raw, plain_vocab) or [raw])
    return final, logic


# ── Bidirectional filter engine ───────────────────────────────────────────────
def apply_filters_except(df_full: pd.DataFrame, skip: str,
                          cats, subcats, tipos, difs,
                          char_set, inc_set, exc_set, logic,
                          max_t, min_r, search_text, tags_filter) -> pd.DataFrame:
    """Apply all filters EXCEPT the one named in `skip`. Used to compute counts."""
    f = df_full.copy()
    if skip != "name" and search_text:
        f = f[f["titulo"].str.contains(search_text, case=False, na=False)]
    if skip != "cats" and cats:
        f = f[f["categoria"].isin(cats)]
    if skip != "subcats" and subcats and "subcategoria" in f.columns:
        f = f[f["subcategoria"].isin(subcats)]
    if skip != "tipos" and tipos and "tipo_cocina" in f.columns:
        f = f[f["tipo_cocina"].isin(tipos)]
    if skip != "difs" and difs:
        f = f[f["dificultad"].isin(difs)]
    if skip != "tags" and tags_filter:
        ts = set(tags_filter)
        f = f[f["titulo"].apply(lambda t: bool(ts & set(ud()["tags"].get(t, []))))]
    if skip != "chars" and char_set:
        f = f[f["_chars"].apply(lambda c: bool(char_set & set(c)))]
    if skip != "inc" and inc_set:
        if "AND" in logic:
            f = f[f["_ct"].apply(lambda t: inc_set.issubset(set(t)))]
        else:
            f = f[f["_ct"].apply(lambda t: bool(inc_set & set(t)))]
    if skip != "exc" and exc_set:
        f = f[f["_ct"].apply(lambda t: not bool(exc_set & set(t)))]
    if skip != "time" and max_t < 999:
        f = f[f["tiempo_total"].apply(time_to_min) <= max_t]
    if skip != "rat" and min_r > 0:
        f = f[f["valoracion_media"] >= min_r]
    return f


def opts_with_counts(values: list, col: str, base: pd.DataFrame) -> list:
    """Turn ['Postres','Carnes'] into ['Postres (42)','Carnes (18)']."""
    vc = base[col].value_counts() if not base.empty else pd.Series(dtype=int)
    return [f"{v} ({vc.get(v,0)})" for v in values]


def chars_with_counts(char_list: list, base: pd.DataFrame) -> list:
    c: Counter = Counter()
    for chars in base["_chars"]:
        c.update(chars)
    return [f"{v} ({c.get(v,0)})" for v in char_list]


with tab2:
    st.subheader("🔍 Explorar Recetas")

    # ── Saved searches ────────────────────────────────────────────────────────
    saved_searches: dict = ud().get("saved_searches", {})
    if saved_searches:
        with st.expander(f"🔖 Búsquedas guardadas ({len(saved_searches)})", expanded=False):
            for sname, sparams in list(saved_searches.items()):
                sc1, sc2, sc3 = st.columns([4, 1, 1])
                with sc1: st.markdown(f"**{sname}**")
                with sc2:
                    if st.button("Cargar", key=f"ss_load_{sname}"):
                        for k, v in sparams.items():
                            st.session_state[k] = v
                        st.rerun()
                with sc3:
                    if st.button("✕", key=f"ss_del_{sname}"):
                        del saved_searches[sname]
                        ud()["saved_searches"] = saved_searches
                        save_ud(); st.rerun()

    # ── Read current accumulator state BEFORE widgets ─────────────────────────
    # These are needed to compute bidirectional counts
    _cats_cur    = st.session_state.get("exp_cats", [])
    _subcats_cur = st.session_state.get("exp_subcats", [])
    _tipos_cur   = st.session_state.get("exp_tipo", [])
    _difs_cur    = st.session_state.get("exp_difs", [])
    _inc_cur     = set(st.session_state.get("_acc_inc", []))
    _exc_cur     = set(st.session_state.get("_acc_exc", []))
    _chars_cur   = set(st.session_state.get("_acc_chars", []))
    _name_cur    = st.session_state.get("exp_name", "")
    _tags_cur    = st.session_state.get("exp_tags", [])
    _time_cur    = st.session_state.get("exp_time", 999)
    _rat_cur     = st.session_state.get("exp_rat", 0.0)
    _logic_cur   = st.session_state.get("exp_logic", "OR — alguno")

    # Base pools for each filter (everything except that filter itself)
    base_cats    = apply_filters_except(df, "cats",    _cats_cur, _subcats_cur, _tipos_cur, _difs_cur, _chars_cur, _inc_cur, _exc_cur, _logic_cur, _time_cur, _rat_cur, _name_cur, _tags_cur)
    base_subcats = apply_filters_except(df, "subcats", _cats_cur, _subcats_cur, _tipos_cur, _difs_cur, _chars_cur, _inc_cur, _exc_cur, _logic_cur, _time_cur, _rat_cur, _name_cur, _tags_cur)
    base_tipos   = apply_filters_except(df, "tipos",   _cats_cur, _subcats_cur, _tipos_cur, _difs_cur, _chars_cur, _inc_cur, _exc_cur, _logic_cur, _time_cur, _rat_cur, _name_cur, _tags_cur)
    base_difs    = apply_filters_except(df, "difs",    _cats_cur, _subcats_cur, _tipos_cur, _difs_cur, _chars_cur, _inc_cur, _exc_cur, _logic_cur, _time_cur, _rat_cur, _name_cur, _tags_cur)
    base_chars   = apply_filters_except(df, "chars",   _cats_cur, _subcats_cur, _tipos_cur, _difs_cur, _chars_cur, _inc_cur, _exc_cur, _logic_cur, _time_cur, _rat_cur, _name_cur, _tags_cur)

    # Build option lists with counts
    all_cats_wc    = opts_with_counts(sorted(df["categoria"].unique()), "categoria", base_cats)
    all_subcats_wc = opts_with_counts(
        sorted(base_subcats["subcategoria"].dropna().unique()) if "subcategoria" in base_subcats.columns else [],
        "subcategoria", base_subcats)
    all_tipos_wc   = opts_with_counts(
        sorted(base_tipos["tipo_cocina"].dropna().unique()) if "tipo_cocina" in base_tipos.columns else [],
        "tipo_cocina", base_tipos)
    all_difs_wc    = opts_with_counts(sorted(df["dificultad"].unique()), "dificultad", base_difs)
    all_chars_wc   = chars_with_counts(char_vocab, base_chars)

    with st.expander("🎛️ Filtros", expanded=True):

        # Row 1 — nombre, categoría, subcategoría
        r1a, r1b, r1c = st.columns([2, 2, 2])
        with r1a:
            search_text = st.text_input("🔎 Nombre", placeholder="paella…", key="exp_name")
        with r1b:
            cats_inc_raw = st.multiselect("📂 Categoría", all_cats_wc,
                                          placeholder="Todas", key="exp_cats")
            cats_inc = [re.sub(r"\s*\(\d+\)$","",v).strip() for v in cats_inc_raw]
        with r1c:
            subcats_inc_raw = st.multiselect("📁 Subcategoría", all_subcats_wc,
                                             placeholder="Todas", key="exp_subcats")
            subcats_inc = [re.sub(r"\s*\(\d+\)$","",v).strip() for v in subcats_inc_raw]

        # Row 2 — tipo cocina, dificultad, etiquetas
        r2a, r2b, r2c = st.columns([2, 2, 2])
        with r2a:
            tipo_inc_raw = st.multiselect("🍴 Tipo cocina", all_tipos_wc,
                                          placeholder="Todos", key="exp_tipo")
            tipo_inc = [re.sub(r"\s*\(\d+\)$","",v).strip() for v in tipo_inc_raw]
        with r2b:
            difs_inc_raw = st.multiselect("💪 Dificultad", all_difs_wc,
                                          placeholder="Todas", key="exp_difs")
            difs_inc = [re.sub(r"\s*\(\d+\)$","",v).strip() for v in difs_inc_raw]
        with r2c:
            all_tags = sorted({t for tags in ud()["tags"].values() for t in tags})
            tags_filter = st.multiselect("🏷️ Mis etiquetas", all_tags,
                                          placeholder="Todas", key="exp_tags") if all_tags else []

        st.markdown("---")

        # Características with bidirectional counts
        char_set, _ = acc_selector(
            "✨ Características", all_chars_wc,
            "_acc_chars", "exp_char_txt", "exp_char_sel", "exp_char_lst",
            chip_color="#f0fdf4", chip_text="#166534")

        st.markdown("---")

        # Ingredientes QUIERO
        inc_set, logic = acc_selector(
            "✅ Ingredientes que QUIERO", canon_list,
            "_acc_inc", "exp_inc_txt", "exp_inc_sel", "exp_inc_lst", "exp_logic",
            chip_color="#e8f4fd", chip_text="#1565c0")

        st.markdown("---")

        # Ingredientes NO QUIERO
        exc_set, _ = acc_selector(
            "🚫 Ingredientes que NO quiero", canon_list,
            "_acc_exc", "exp_exc_txt", "exp_exc_sel", "exp_exc_lst",
            chip_color="#fee2e2", chip_text="#991b1b")

        st.markdown("---")

        r4a, r4b, r4c = st.columns([2, 2, 2])
        with r4a:
            max_t = st.select_slider("⏱️ Tiempo máx.",
                                     [15,30,45,60,90,120,999], value=999,
                                     format_func=lambda x:"Sin límite" if x==999 else f"{x}m",
                                     key="exp_time")
        with r4b:
            min_r = st.slider("⭐ Valoración mín.", 0.0, 5.0, 0.0, 0.5, key="exp_rat")
        with r4c:
            show_hidden = st.checkbox("Mostrar recetas ocultas", key="exp_show_hidden")

        st.markdown("---")
        sv1, sv2 = st.columns([3,1])
        with sv1:
            save_name = st.text_input("💾 Guardar búsqueda como…",
                                      placeholder="Mis postres rápidos…",
                                      key="exp_save_name", label_visibility="collapsed")
        with sv2:
            if st.button("💾 Guardar", key="exp_save_btn") and save_name.strip():
                snap = {
                    "exp_name": search_text, "exp_cats": cats_inc_raw,
                    "exp_subcats": subcats_inc_raw, "exp_tipo": tipo_inc_raw,
                    "exp_difs": difs_inc_raw, "exp_time": max_t, "exp_rat": min_r,
                    "_acc_inc":   list(st.session_state.get("_acc_inc", [])),
                    "_acc_exc":   list(st.session_state.get("_acc_exc", [])),
                    "_acc_chars": list(st.session_state.get("_acc_chars", [])),
                }
                ud().setdefault("saved_searches", {})[save_name.strip()] = snap
                save_ud(); st.success(f"✓ Guardada"); st.rerun()

    # ── Apply filters ─────────────────────────────────────────────────────────
    filt = df.copy()
    if search_text:
        filt = filt[filt["titulo"].str.contains(search_text, case=False, na=False)]
    if cats_inc:
        filt = filt[filt["categoria"].isin(cats_inc)]
    if subcats_inc and "subcategoria" in filt.columns:
        filt = filt[filt["subcategoria"].isin(subcats_inc)]
    if tipo_inc and "tipo_cocina" in filt.columns:
        filt = filt[filt["tipo_cocina"].isin(tipo_inc)]
    if difs_inc:
        filt = filt[filt["dificultad"].isin(difs_inc)]
    if tags_filter:
        ts = set(tags_filter)
        filt = filt[filt["titulo"].apply(lambda t: bool(ts & set(ud()["tags"].get(t, []))))]
    if char_set:
        filt = filt[filt["_chars"].apply(lambda c: bool(char_set & set(c)))]
    if inc_set:
        if "AND" in logic:
            filt = filt[filt["_ct"].apply(lambda t: inc_set.issubset(set(t)))]
        else:
            filt = filt[filt["_ct"].apply(lambda t: bool(inc_set & set(t)))]
    if exc_set:
        filt = filt[filt["_ct"].apply(lambda t: not bool(exc_set & set(t)))]
    if max_t < 999:
        filt = filt[filt["tiempo_total"].apply(time_to_min) <= max_t]
    if min_r > 0:
        filt = filt[filt["valoracion_media"] >= min_r]

    hidden_count = len(set(ud().get("hidden",[])) & set(filt["titulo"].tolist())) if not filt.empty else 0
    st.caption(f"**{len(filt):,}** recetas encontradas"
               + (f" · {hidden_count} ocultas" if hidden_count and not show_hidden else ""))

    # ── Añadir al siguiente hueco desde Explorar ──────────────────────────────
    if not filt.empty:
        ndia2, nmeal2 = next_free_slot(ud()["planner"])
        slot_label = f"{ndia2} / {nmeal2.split(None,1)[-1]}" if ndia2 != "_reserva" else nmeal2
        st.caption(f"⏭️ Siguiente hueco libre: **{slot_label}** · "
                   f"Usa el botón ➕ dentro de cada receta para añadir ahí directamente")

    recipe_grid(filt, "exp", hide_hidden=not show_hidden)

# TAB 3 — GENERADOR DE MENÚ
# ══════════════════════════════════════════════════════════════════════════════

def pick_recipe(pool: pd.DataFrame, exclude_titles: set = None,
                tipo: str = None, seed: int = None) -> dict | None:
    """Pick a random recipe from pool matching optional tipo_cocina filter."""
    sub = pool.copy()
    if exclude_titles:
        sub = sub[~sub["titulo"].isin(exclude_titles)]
    if tipo and "tipo_cocina" in sub.columns:
        t = sub[sub["tipo_cocina"] == tipo]
        if not t.empty: sub = t
    if sub.empty: return None
    row = sub.sample(1, random_state=seed).iloc[0]
    return {"titulo": row["titulo"], "meal": "☀️ Comida",
            "comensales": int(row["comensales"]),
            "ingredientes": row["ingredientes"],
            "categoria": row.get("categoria",""),
            "tipo_cocina": row.get("tipo_cocina",""),
            "tiempo_total": row.get("tiempo_total",""),
            "_idx": int(row.name)}

MEAL_TIPO_MAP = {
    "🌅 Desayuno": ["Desayuno","Merienda"],
    "☀️ Comida":   ["Plato principal","Entrante","Acompañamiento"],
    "🌙 Cena":     ["Cena","Plato principal","Entrante"],
}


with tab3:
    st.subheader("🍽️ Generador de Menú Semanal")
    st.caption("Genera sugerencias a partir de tus listas de ingredientes. "
               "Sustituye platos uno a uno o regenera toda la semana.")

    # ── Config ────────────────────────────────────────────────────────────────
    gc1, gc2 = st.columns([2, 3])
    with gc1:
        my_lists = list(ud().get("ing_lists", {}).keys())
        if not my_lists:
            st.warning("Crea primero una lista en 🧺 Mis Listas para generar menús basados en ingredientes.")
            st.stop()
        chosen_list = st.selectbox("Lista de ingredientes base", my_lists, key="gen_list")
        extra_gen = st.slider("Ingredientes extra permitidos", 0, 10, 3,
                              format="+%d", key="gen_extra")

    with gc2:
        st.markdown("**Personalizar turnos (opcional)**")
        st.caption("Deja en blanco para que el motor elija. O indica el tipo de plato por turno.")
        gcols = st.columns(3)
        meal_prefs: dict = {}
        tipo_options = ["(automático)"] + sorted(df["tipo_cocina"].dropna().unique().tolist()) if "tipo_cocina" in df.columns else ["(automático)"]
        for mi, meal in enumerate(MEAL_SLOTS):
            with gcols[mi]:
                meal_prefs[meal] = st.selectbox(meal, tipo_options, key=f"gen_pref_{mi}")

    # ── Build recipe pool from list ───────────────────────────────────────────
    list_ings = set(ud()["ing_lists"].get(chosen_list, []))
    _ea_gen = extra_gen
    pool = df[df["_ct"].apply(
        lambda t, _ls=list_ings, _e=_ea_gen:
            bool(set(t) & _ls) and len(set(t) - _ls) <= _e
    )].copy()

    st.caption(f"🎲 Pool de recetas para «{chosen_list}»: **{len(pool):,} recetas** disponibles")

    if pool.empty:
        st.warning("No hay recetas con esos ingredientes. Amplía los ingredientes extra permitidos.")
    else:
        # ── Generate / Regenerate ─────────────────────────────────────────────
        gen_key = "_gen_menu"
        if gen_key not in st.session_state:
            st.session_state[gen_key] = {}  # {(dia, meal): recipe_dict}

        gen_menu: dict = st.session_state[gen_key]

        btn_regen, btn_clear = st.columns([2, 1])
        with btn_regen:
            if st.button("🎲 Generar / Regenerar semana completa", type="primary", key="gen_all"):
                used = set()
                new_menu = {}
                import random
                seed_base = random.randint(0, 99999)
                for di, dia in enumerate(DIAS):
                    for mi, meal in enumerate(MEAL_SLOTS):
                        tipo_pref = meal_prefs.get(meal, "(automático)")
                        tipo = None if tipo_pref == "(automático)" else tipo_pref
                        # If no pref, use meal→tipo mapping
                        if not tipo:
                            tipo_candidates = MEAL_TIPO_MAP.get(meal, [])
                            # Try each candidate type
                            picked = None
                            for tc in tipo_candidates:
                                picked = pick_recipe(pool, used, tipo=tc,
                                                     seed=seed_base + di*10 + mi)
                                if picked: break
                            if not picked:
                                picked = pick_recipe(pool, used, seed=seed_base+di*10+mi)
                        else:
                            picked = pick_recipe(pool, used, tipo=tipo,
                                                 seed=seed_base+di*10+mi)
                            if not picked:
                                picked = pick_recipe(pool, used, seed=seed_base+di*10+mi)
                        if picked:
                            picked["meal"] = meal
                            new_menu[(dia, meal)] = picked
                            used.add(picked["titulo"])
                st.session_state[gen_key] = new_menu
                st.rerun()
        with btn_clear:
            if st.button("🗑️ Limpiar sugerencias", key="gen_clear"):
                st.session_state[gen_key] = {}; st.rerun()

        if not gen_menu:
            st.info("Pulsa «Generar semana completa» para empezar.")
        else:
            # ── Display generated menu as grid ────────────────────────────────
            st.markdown("---")
            st.markdown("**Sugerencias generadas** · Reemplaza huecos individuales o añade al planner:")

            for dia in DIAS:
                st.markdown(f"#### {dia}")
                meal_cols = st.columns(3)
                for mi, meal in enumerate(MEAL_SLOTS):
                    with meal_cols[mi]:
                        key = (dia, meal)
                        rec = gen_menu.get(key)
                        meal_icon = meal.split()[0]
                        st.markdown(f"**{meal_icon} {meal.split(None,1)[1] if ' ' in meal else meal}**")

                        if rec:
                            # Full recipe card
                            row_match = df[df["titulo"] == rec["titulo"]]
                            if not row_match.empty:
                                recipe_card(row_match.iloc[0], f"gen_{dia}_{mi}")
                            else:
                                st.markdown(f"**{rec['titulo']}**")
                            # Replace button
                            if st.button("🔀 Sugerir otro", key=f"gen_rep_{dia}_{mi}",
                                         use_container_width=True):
                                used_others = {v["titulo"] for k,v in gen_menu.items()
                                               if k != key}
                                tipo_pref = meal_prefs.get(meal, "(automático)")
                                tipo = None if tipo_pref == "(automático)" else tipo_pref
                                if not tipo:
                                    new_r = None
                                    for tc in MEAL_TIPO_MAP.get(meal, []):
                                        new_r = pick_recipe(pool, used_others, tipo=tc)
                                        if new_r: break
                                    if not new_r:
                                        new_r = pick_recipe(pool, used_others)
                                else:
                                    new_r = pick_recipe(pool, used_others, tipo=tipo)
                                    if not new_r:
                                        new_r = pick_recipe(pool, used_others)
                                if new_r:
                                    new_r["meal"] = meal
                                    gen_menu[key] = new_r
                                    st.session_state[gen_key] = gen_menu
                                st.rerun()
                        else:
                            st.caption("Sin sugerencia disponible")
                            if st.button("🎲 Buscar", key=f"gen_find_{dia}_{mi}",
                                         use_container_width=True):
                                new_r = pick_recipe(pool, set())
                                if new_r:
                                    new_r["meal"] = meal
                                    gen_menu[key] = new_r
                                    st.session_state[gen_key] = gen_menu; st.rerun()

            # ── Bulk add to planner ───────────────────────────────────────────
            st.markdown("---")
            if st.button("📅 Añadir TODAS las sugerencias al planner", key="gen_add_all"):
                count = 0
                for (dia, meal), rec in gen_menu.items():
                    row_match = df[df["titulo"] == rec["titulo"]]
                    if not row_match.empty:
                        ndia, nmeal = next_free_slot(ud()["planner"])
                        add_to_planner(row_match.iloc[0], ndia, nmeal)
                        count += 1
                st.success(f"✓ {count} recetas añadidas al planner")

# TAB 3 — FAVORITOS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("⭐ Favoritos")
    favs = ud()["favorites"]
    if not favs:
        st.info("Aún no tienes favoritas. En Explorar pulsa ☆ Favorito dentro de cada receta.")
    else:
        fav_df = df[df["titulo"].isin(favs)]
        st.caption(f"{len(fav_df)} recetas guardadas")
        recipe_grid(fav_df, "fav", hide_hidden=False)

    # Hidden recipes management
    hidden = ud().get("hidden",[])
    if hidden:
        st.markdown("---")
        with st.expander(f"🚫 Recetas ocultas ({len(hidden)}) — click para gestionar"):
            for t in hidden:
                hc1, hc2 = st.columns([4,1])
                with hc1: st.markdown(f"- {t}")
                with hc2:
                    if st.button("Mostrar", key=f"unhide_{t[:20]}"):
                        ud()["hidden"].remove(t); save_ud(); st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — MIS LISTAS
# ══════════════════════════════════════════════════════════════════════════════

def parse_text_list(text: str, canon_list: list) -> tuple:
    """
    Dado un texto libre con ingredientes separados por comas (ej: "Plátano, Piña, Pera"),
    devuelve:
      - resolved: lista de ingredientes canónicos que coinciden (por substring)
      - not_found: términos que no han tenido ninguna coincidencia
    Acepta variantes: "plátano" matchea "plátano macho", "plátano verde", etc.
    """
    terms = [t.strip().lower() for t in re.split(r"[,\n]+", text) if t.strip()]
    resolved, not_found = [], []
    for term in terms:
        matches = [c for c in canon_list if term in c or c in term]
        if matches:
            for m in matches:
                if m not in resolved:
                    resolved.append(m)
        else:
            not_found.append(term)
    return resolved, not_found


with tab5:
    st.subheader("🧺 Mis Listas de Ingredientes")
    st.caption("Pega una lista de ingredientes separados por comas y la app busca todas sus variantes automáticamente.")

    ing_lists = ud().get("ing_lists",{})

    with st.expander("➕ Nueva lista", expanded=not ing_lists):
        lna, lnb = st.columns([3,1])
        with lna: new_list_name = st.text_input("Nombre de la lista", placeholder="Frutas, Nevera, Bebé…", key="nl_nm")
        with lnb:
            st.write(""); st.write("")
            if st.button("Crear", type="primary", key="nl_cr"):
                nm = new_list_name.strip()
                if nm and nm not in ing_lists:
                    ing_lists[nm] = []; ud()["ing_lists"] = ing_lists; save_ud(); st.rerun()
                elif nm in ing_lists: st.warning("Ya existe.")
                else: st.warning("Escribe un nombre.")

    if not ing_lists:
        st.info("Crea tu primera lista arriba.")
    else:
        for list_name, list_ings in list(ing_lists.items()):
            lk = re.sub(r"[^\w]", "_", list_name)  # safe key, full name
            st.markdown(f'<div class="lcard"><b>🧺 {list_name}</b> · {len(list_ings)} ingredientes</div>',
                        unsafe_allow_html=True)

            with st.expander(f"Editar «{list_name}»"):

                # ── Pegar lista de texto libre ─────────────────────────────
                st.markdown("**Opción 1 — Pegar lista de texto**")
                paste_text = st.text_area(
                    "Pega ingredientes separados por comas",
                    placeholder="Plátano, Piña, Pera, Naranja, Fresa, Manzana…\n\nAcepta variantes: 'plátano' también añade 'plátano macho', 'plátano verde', etc.",
                    height=100,
                    key=f"lpaste_{lk}"
                )
                if st.button("🔍 Resolver y previsualizar", key=f"lpreview_{lk}") and paste_text.strip():
                    resolved, not_found = parse_text_list(paste_text, canon_list)
                    new_ones = [r for r in resolved if r not in list_ings]
                    st.session_state[f"_preview_{lk}"] = (new_ones, not_found)

                if f"_preview_{lk}" in st.session_state:
                    new_ones, not_found = st.session_state[f"_preview_{lk}"]
                    if new_ones:
                        st.success(f"✓ {len(new_ones)} ingredientes encontrados con sus variantes")
                        # Show as multiselect so user can deselect unwanted
                        confirmed = st.multiselect(
                            "Confirmar qué añadir (desmarca los que no quieras)",
                            options=new_ones,
                            default=new_ones,
                            key=f"lconfirm_{lk}"
                        )
                        if st.button(f"➕ Añadir {len(confirmed)} a la lista", key=f"laddconfirm_{lk}",
                                     type="primary"):
                            ing_lists[list_name].extend(confirmed)
                            ud()["ing_lists"] = ing_lists; save_ud()
                            st.session_state.pop(f"_preview_{lk}", None); st.rerun()
                    if not_found:
                        st.warning(f"No encontrados en el dataset: {', '.join(not_found)}")

                st.markdown("---")

                # ── Búsqueda por palabra individual ───────────────────────
                st.markdown("**Opción 2 — Buscar por palabra**")
                le1, le2 = st.columns([3,1])
                with le1:
                    add_txt = st.text_input("Escribe una palabra",
                                            placeholder="'aceite' → muestra todos los tipos…",
                                            key=f"ladd_txt_{lk}")
                    opts = [i for i in (expand_by_text(add_txt, canon_list) if add_txt else canon_list)
                            if i not in list_ings]
                    new_ing = st.multiselect("Seleccionar para añadir", opts,
                                             placeholder="Escribe para filtrar…",
                                             key=f"ladd_sel_{lk}")
                with le2:
                    st.write(""); st.write("")
                    if st.button("Añadir", key=f"ladd_btn_{lk}") and new_ing:
                        ing_lists[list_name].extend([i for i in new_ing if i not in list_ings])
                        ud()["ing_lists"] = ing_lists; save_ud(); st.rerun()

                st.markdown("---")

                # ── Ingredientes actuales ──────────────────────────────────
                if list_ings:
                    st.markdown(f"**Ingredientes actuales ({len(list_ings)}):**")
                    # Use index as part of key to avoid duplicate key errors
                    chunks = [list(enumerate(list_ings))[i:i+4]
                              for i in range(0, len(list_ings), 4)]
                    for chunk in chunks:
                        rcols = st.columns(len(chunk))
                        for ci, (orig_idx, ing) in enumerate(chunk):
                            with rcols[ci]:
                                if st.button(f"✕ {ing}",
                                             key=f"lrm_{lk}_{orig_idx}",
                                             use_container_width=True):
                                    ing_lists[list_name].pop(orig_idx)
                                    ud()["ing_lists"] = ing_lists; save_ud(); st.rerun()
                    if st.button("🗑️ Vaciar lista", key=f"lempty_{lk}"):
                        ing_lists[list_name] = []
                        ud()["ing_lists"] = ing_lists; save_ud(); st.rerun()
                else:
                    st.caption("Lista vacía.")

                st.markdown("---")
                if st.button(f"🗑️ Eliminar lista «{list_name}»", key=f"ldel_{lk}"):
                    del ing_lists[list_name]; ud()["ing_lists"] = ing_lists; save_ud(); st.rerun()

            # ── Buscar recetas ─────────────────────────────────────────────
            if list_ings:
                st.markdown(f"**Buscar recetas con «{list_name}»**")
                extra = st.slider("Ingredientes extra permitidos",
                                  0, 10, 0, key=f"lex_{lk}", format="+%d")
                ls = set(list_ings)
                _ea = extra
                matched = df[df["_ct"].apply(
                    lambda t, _ls=ls, _e=_ea: bool(set(t) & _ls) and len(set(t) - _ls) <= _e
                )]
                st.caption(f"{'🎯 Exacto' if extra==0 else f'+{extra} ingrediente(s) extra'} · "
                           f"**{len(matched):,} recetas**")
                if not matched.empty:
                    recipe_grid(matched, f"li_{lk}")
            st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — COMPRA
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.subheader("🛒 Lista de la Compra")
    planned_entries = [e for entries in ud()["planner"].values() for e in entries]

    if not planned_entries:
        st.info("Añade recetas al planner para generar la lista.")
    else:
        st.caption(f"Basado en **{len(planned_entries)} recetas** planificadas")
        raw_c: Counter = Counter()
        for entry in planned_entries:
            for ing in parse_display(entry.get("ingredientes","")):
                raw_c[ing.lower().strip()] += 1

        shop_exc = st.multiselect("🚫 Ya lo tengo en casa",
                                  sorted(raw_c.keys()),
                                  placeholder="Escribe para buscar…",
                                  key="shop_exc")
        exc_set = {e.lower() for e in shop_exc}
        active = {k:v for k,v in raw_c.items() if k not in exc_set}

        CAT_KW = {
            "🥩 Carnes y proteínas": ["pollo","ternera","cerdo","carne","pechuga","muslo","bistec",
                "tocino","bacon","jamón","chorizo","salchicha","atún","salmón","merluza",
                "bacalao","gambas","camarones","huevo","pavo"],
            "🥦 Verduras": ["cebolla","tomate","ajo","pimiento","zanahoria","calabacín","patata",
                "lechuga","espinaca","acelga","champiñon","berenjena","puerro","apio",
                "pepino","coliflor","brócoli","aguacate","maíz","judía","guisante"],
            "🍋 Frutas": ["limón","naranja","manzana","plátano","fresa","mango","piña",
                "uva","kiwi","melocotón","pera","ciruela","pomelo"],
            "🥛 Lácteos": ["leche","nata","mantequilla","queso","yogur","crema",
                "mozzarella","parmesano"],
            "🌾 Cereales y legumbres": ["harina","arroz","pasta","macarrón","espagueti","pan",
                "avena","lenteja","garbanzo","frijol","alubia","quinoa"],
            "🫙 Aceites y salsas": ["aceite","vinagre","soja","mayonesa","ketchup","salsa",
                "caldo","vino","mostaza"],
            "🧂 Especias": ["sal","pimienta","orégano","tomillo","romero","laurel","comino",
                "pimentón","curry","canela","perejil","cilantro","albahaca","azafrán",
                "nuez moscada","azúcar"],
        }

        def cat_of(i):
            il = i.lower()
            for c,kws in CAT_KW.items():
                if any(k in il for k in kws): return c
            return "🍬 Otros"

        by_cat: dict = {}
        for ing,cnt in sorted(active.items()):
            by_cat.setdefault(cat_of(ing),[]).append((ing,cnt))

        export = ["LISTA DE LA COMPRA","="*30]
        for cat,items in by_cat.items():
            export.append(f"\n{cat}")
            for ing,cnt in items:
                export.append(f"  ☐ {'('+str(cnt)+'x) ' if cnt>1 else ''}{ing}")
        st.download_button("📥 Exportar .txt", "\n".join(export),
                           "lista_compra.txt", "text/plain")

        if "chk" not in st.session_state: st.session_state.chk = set()
        total_i = sum(len(v) for v in by_cat.values())
        done_i  = len([i for i in st.session_state.chk if i in active])
        st.progress(done_i/total_i if total_i else 0,
                    text=f"Completado: {done_i}/{total_i}")
        if st.button("↺ Desmarcar todo"): st.session_state.chk = set(); st.rerun()

        for cat,items in by_cat.items():
            if not items: continue
            st.markdown(f'<div class="shopcat">{cat}</div>', unsafe_allow_html=True)
            for ing,cnt in items:
                prefix = f"({cnt}x) " if cnt>1 else ""
                chk = st.checkbox(f"{prefix}{ing}", value=ing in st.session_state.chk,
                                  key=f"chk_{ing[:50]}")
                if chk: st.session_state.chk.add(ing)
                else:   st.session_state.chk.discard(ing)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — HISTORIAL
# ══════════════════════════════════════════════════════════════════════════════
with tab7:
    st.subheader("📖 Historial de Menús")
    history = ud().get("history",[])
    if not history:
        st.info("Guarda la semana actual desde el Planner con 'Guardar semana en historial'.")
    else:
        for i, entry in enumerate(reversed(history)):
            idx = len(history) - 1 - i
            with st.expander(f"📅 {entry['week']}"):
                days = entry.get("days",{})
                cols7 = st.columns(7)
                for di, dia in enumerate(DIAS):
                    with cols7[di]:
                        st.markdown(f"**{dia[:3]}**")
                        for e in days.get(dia,[]):
                            st.markdown(f'<div class="pr">{e["meal"].split()[0]} {e["titulo"][:20]}…</div>',
                                        unsafe_allow_html=True)

                hb1, hb2 = st.columns([2,2])
                with hb1:
                    if st.button("♻️ Cargar esta semana en el planner", key=f"hload_{idx}"):
                        ud()["planner"] = {d: list(days.get(d,[])) for d in DIAS}
                        save_ud(); st.success("✓ Semana cargada en el planner"); st.rerun()
                with hb2:
                    if st.button("🗑️ Borrar del historial", key=f"hdel_{idx}"):
                        ud()["history"].pop(idx); save_ud(); st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — IA
# ══════════════════════════════════════════════════════════════════════════════
with tab8:
    st.subheader("🤖 Sugerencias con IA")
    st.caption("Powered by **Groq** (gratuito) · Llama 3.3 70B · Busca en tu dataset real")

    try:    gkey = st.secrets.get("GROQ_API_KEY","")
    except: gkey = ""
    api_key = gkey or st.text_input("API Key de Groq", type="password",
                                     help="Gratis en console.groq.com")
    if not api_key:
        st.info("1. [console.groq.com](https://console.groq.com) → crea cuenta\n"
                "2. API Keys → Create API Key\n"
                "3. Pégala arriba\n\n"
                "Para no introducirla: `.streamlit/secrets.toml` → `GROQ_API_KEY='gsk_...'`")

    mode = st.radio("¿Qué quieres hacer?", [
        "🥬 Tengo estos ingredientes, ¿qué cocino?",
        "🏠 ¿Qué cocino con mis listas? (sin IA)",
        "📅 Generar menú semanal equilibrado",
        "🔄 Sustituir un ingrediente",
    ])

    if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
        user_input = st.text_area("¿Qué tienes en casa?",
                                  placeholder="pollo, patatas, cebolla…", height=70)
        extra = st.text_input("Restricciones (opcional)", placeholder="sin gluten…")

    elif mode == "🏠 ¿Qué cocino con mis listas? (sin IA)":
        st.caption("Busca directamente en el dataset sin gastar tokens de IA.")
        my_lists = list(ud().get("ing_lists",{}).keys())
        if not my_lists:
            st.info("Crea primero una lista en 🧺 Mis Listas.")
        else:
            chosen_lists = st.multiselect("Usar ingredientes de estas listas", my_lists)
            extra_allow  = st.slider("Ingredientes extra permitidos", 0, 10, 2, format="+%d")
            if chosen_lists:
                combined = set()
                for ln in chosen_lists:
                    combined.update(ud()["ing_lists"].get(ln,[]))
                _ea2 = extra_allow
                no_ai = df[df["_ct"].apply(
                    lambda t, _ls=combined, _e=_ea2:
                        bool(set(t)&_ls) and len(set(t)-_ls)<=_e
                )]
                st.caption(f"**{len(no_ai):,} recetas** con esos ingredientes (+{extra_allow} extra)")
                recipe_grid(no_ai, "noai")
        mode = None  # skip AI button

    elif mode == "📅 Generar menú semanal equilibrado":
        user_input = ""
        extra = st.text_area("Preferencias", placeholder="4 personas, sin pescado…", height=70)
    else:
        user_input = st.text_input("Ingrediente a sustituir", placeholder="nata líquida")
        extra = st.text_input("Contexto", placeholder="carbonara, sin lactosa")

    if mode and st.button("✨ Preguntar a la IA", type="primary", disabled=not api_key):
        def search_ds(kws, max_r=40):
            if not kws: return df.sample(min(max_r,len(df)))
            mask = pd.Series([False]*len(df), index=df.index)
            for kw in kws:
                kw = kw.strip().lower()
                if len(kw)<2: continue
                mask |= df["_ct"].apply(lambda t: any(kw in x for x in t))
                mask |= df["titulo"].str.lower().str.contains(kw, na=False)
            r = df[mask]
            return r.head(max_r) if not r.empty else df.sample(min(max_r,len(df)))

        def to_txt(sub, mx=25):
            lines=[]
            for _,r in sub.head(mx).iterrows():
                ing = str(r.get("ingredientes","") or "")[:160]
                lines.append(f"- {r.get('titulo','?')} | {r.get('categoria','?')} | "
                             f"{r.get('tiempo_total','?')} | Ingredientes: {ing}")
            return "\n".join(lines)

        if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
            kws = [w.strip() for w in user_input.replace(","," ").split() if len(w.strip())>2]
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
            muestra = pd.concat([
                g.sample(min(6,len(g))) for _,g in df.groupby("categoria", group_keys=False)
            ]).reset_index(drop=True)
            prompt = (
                "Eres nutricionista y chef. SOLO puedes usar estas recetas reales. "
                "NO inventes recetas fuera de la lista.\n\n"
                f"RECETAS:\n{to_txt(muestra,50)}\n\n"
                f"Preferencias: {extra or 'ninguna'}.\n"
                "Diseña menú lunes-domingo (comida+cena) con nombres exactos. "
                "Variado entre categorías. Nota final sobre equilibrio nutricional. Español."
            )
        else:
            prompt = (f"Quiero sustituir '{user_input}' en: {extra or 'una receta'}.\n"
                      "Sugiere 3 sustitutos: nombre, proporción, efecto. Español.")

        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            with st.spinner("Consultando IA…"):
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role":"user","content":prompt}],
                    max_tokens=1200, temperature=0.3)
            st.markdown("### 💬 Respuesta")
            st.markdown(resp.choices[0].message.content)
            if "cands" in dir(): st.caption(f"🔍 Analizadas {len(cands)} recetas del dataset.")
        except ImportError: st.error("`pip install groq`")
        except Exception as e: st.error(f"Error Groq: {e}")

    if mode: st.caption("Tu API key no se almacena. `.streamlit/secrets.toml` para uso frecuente.")
