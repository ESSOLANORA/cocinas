import streamlit as st
import pandas as pd
import re
import json
from pathlib import Path
import os

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🍽️ Planificador de Recetas",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Mobile-friendly base */
[data-testid="stAppViewContainer"] { padding-top: 1rem; }
.main .block-container { padding: 1rem 1.5rem 2rem; max-width: 960px; }

/* Tabs */
[data-testid="stTabs"] button { font-size: 0.85rem; padding: 0.4rem 0.8rem; }

/* Recipe cards */
.recipe-card {
    background: #f8f9fa;
    border: 1px solid #e0e0e0;
    border-radius: 12px;
    padding: 0.9rem;
    margin-bottom: 0.8rem;
    transition: box-shadow 0.2s;
}
.recipe-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.recipe-title { font-weight: 700; font-size: 1rem; margin-bottom: 0.3rem; color: #1a1a2e; }
.recipe-meta { font-size: 0.78rem; color: #666; }
.recipe-badge {
    display: inline-block;
    background: #e8f4fd;
    color: #1565c0;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.72rem;
    margin-right: 4px;
    margin-top: 4px;
}

/* Planner grid */
.day-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 0.5rem 0.8rem;
    border-radius: 8px 8px 0 0;
    font-weight: 600;
    font-size: 0.9rem;
}
.day-box {
    border: 1px solid #e0e0e0;
    border-top: none;
    border-radius: 0 0 8px 8px;
    padding: 0.6rem;
    min-height: 80px;
    background: white;
    margin-bottom: 0.5rem;
}
.planned-recipe {
    background: #f0fdf4;
    border: 1px solid #86efac;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 0.8rem;
    margin: 3px 0;
    color: #166534;
}

/* Shopping list */
.shop-category { font-weight: 700; color: #7c3aed; margin-top: 1rem; font-size: 0.9rem; }
.shop-item { font-size: 0.88rem; padding: 3px 0; }

/* Stars */
.stars { color: #f59e0b; font-size: 0.85rem; }

/* Hide Streamlit branding on mobile */
footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# ── Data loading & caching ─────────────────────────────────────────────────────
PLANNER_FILE = Path("planner_data.json")

@st.cache_data(show_spinner="Cargando recetas…")
def load_data(file_path: str) -> pd.DataFrame:
    ext = Path(file_path).suffix.lower()
    if ext == ".csv":
        # Try common encodings
        for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
            try:
                df = pd.read_csv(file_path, encoding=enc, low_memory=False)
                break
            except UnicodeDecodeError:
                continue
    else:
        df = pd.read_excel(file_path, engine="openpyxl")

    # Normalize columns
    df["titulo"] = df["titulo"].fillna("Sin título")
    df["categoria"] = df["categoria"].fillna("Otras")
    df["subcategoria"] = df["subcategoria"].fillna("")
    df["dificultad"] = df["dificultad"].fillna("Sin datos")
    df["tiempo_total"] = df["tiempo_total"].fillna("")
    df["comensales"] = pd.to_numeric(df["comensales"], errors="coerce").fillna(4).astype(int)
    df["valoracion_media"] = pd.to_numeric(df["valoracion_media"], errors="coerce").fillna(0)
    df["calorias"] = pd.to_numeric(df["calorias"], errors="coerce").fillna(0)
    df["ingredientes"] = df["ingredientes"].fillna("")
    df["imagen_url"] = df["imagen_url"].fillna("")

    # Ingredient tokens for fast search
    df["_ing_tokens"] = df["ingredientes"].apply(_tokenize_ingredients)
    return df


def _tokenize_ingredients(ing_str: str) -> list[str]:
    """Extract searchable ingredient names from raw string."""
    if not ing_str:
        return []
    items = ing_str.split(" | ")
    tokens = []
    for item in items:
        item = re.sub(r"^[\d½¼¾/.,\s]+", "", item)
        item = re.sub(
            r"^(?:kilogramo[s]?|gramo[s]?|litro[s]?|mililitro[s]?|cucharada[s]?|"
            r"cucharadita[s]?|cucharón[es]?|taza[s]?|vaso[s]?|copa[s]?|lata[s]?|"
            r"unidad[es]?|pieza[s]?|trozo[s]?|rama[s]?|manojo[s]?|pizca[s]?|"
            r"chorro[s]?|puñado[s]?|rebanada[s]?|centímetro[s]?|diente[s]?|"
            r"paquete[s]?|sobre[s]?|pellizco[s]?)\s+(?:de\s+)?",
            "", item, flags=re.IGNORECASE
        )
        item = re.sub(r"^(?:sopera[s]?|postre[s]?)\s+de\s+", "", item, flags=re.IGNORECASE)
        item = re.sub(r"^de\s+", "", item, flags=re.IGNORECASE)
        item = item.strip().lower()
        if len(item) > 2 and not item.startswith("##") and not item.startswith("para"):
            tokens.append(item)
    return tokens


def parse_ingredients_display(ing_str: str) -> list[str]:
    """Return clean list of ingredients for display."""
    if not ing_str:
        return []
    return [i.strip() for i in ing_str.split(" | ") if i.strip() and not i.strip().startswith("##")]


def time_to_minutes(t: str) -> int:
    if not t:
        return 9999
    m = re.match(r"(?:(\d+)h\s*)?(?:(\d+)m)?", t)
    if not m:
        return 9999
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    return h * 60 + mins


def star_display(rating: float) -> str:
    full = int(round(rating))
    return "★" * full + "☆" * (5 - full)


# ── Planner persistence ────────────────────────────────────────────────────────
def load_planner() -> dict:
    if PLANNER_FILE.exists():
        return json.loads(PLANNER_FILE.read_text())
    return {d: [] for d in DIAS}


def save_planner(data: dict):
    PLANNER_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MEAL_SLOTS = ["🌅 Desayuno", "☀️ Comida", "🌙 Cena"]

# ── App state ──────────────────────────────────────────────────────────────────
if "planner" not in st.session_state:
    st.session_state.planner = load_planner()

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🍽️ Planificador de Recetas")

# ── Dataset selector ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuración")
    uploaded = st.file_uploader("Cargar dataset", type=["xlsx", "csv"],
                                help="Acepta .xlsx y .csv")
    dataset_path = None

    if uploaded:
        ext = Path(uploaded.name).suffix.lower()
        save_name = f"dataset{ext}"
        with open(save_name, "wb") as f:
            f.write(uploaded.read())
        dataset_path = save_name
        st.success(f"Dataset cargado ✓ ({uploaded.name})")

    st.markdown("---")
    st.caption("O coloca tu archivo como `dataset.csv` o `dataset.xlsx` en la misma carpeta que `app.py`.")

# ── Load data ──────────────────────────────────────────────────────────────────
if not dataset_path:
    for candidate in ["dataset.csv", "dataset.xlsx"]:
        if Path(candidate).exists():
            dataset_path = candidate
            break

if not dataset_path:
    st.info("👆 Sube tu dataset desde el menú lateral para empezar. En local, coloca el archivo como `dataset.xlsx` junto a `app.py`.")
    st.stop()

try:
    df = load_data(dataset_path)
except Exception as e:
    st.error(f"Error cargando el dataset: {e}")
    st.stop()

st.caption(f"📊 {len(df):,} recetas cargadas · {df['categoria'].nunique()} categorías")

# ── Main tabs ──────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📅 Planner", "🔍 Explorar", "🛒 Compra", "🤖 IA"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — PLANNER SEMANAL
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("📅 Planificador Semanal")

    col_add, col_clear = st.columns([3, 1])
    with col_clear:
        if st.button("🗑️ Limpiar semana", use_container_width=True):
            st.session_state.planner = {d: [] for d in DIAS}
            save_planner(st.session_state.planner)
            st.rerun()

    # ── Add recipe to planner ──────────────────────────────────────────────────
    with st.expander("➕ Añadir receta al planner", expanded=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            search_planner = st.text_input("Buscar receta", placeholder="ej: pollo, paella…", key="plan_search")
        with c2:
            day_sel = st.selectbox("Día", DIAS, key="plan_day")
        with c3:
            meal_sel = st.selectbox("Momento", MEAL_SLOTS, key="plan_meal")

        if search_planner:
            mask = df["titulo"].str.contains(search_planner, case=False, na=False)
            results = df[mask].head(8)
            if results.empty:
                st.caption("Sin resultados.")
            else:
                for _, row in results.iterrows():
                    cols = st.columns([5, 1])
                    with cols[0]:
                        st.markdown(f"**{row['titulo']}** · {row['categoria']} · {row['tiempo_total']}")
                    with cols[1]:
                        if st.button("＋", key=f"add_{row['titulo'][:20]}_{day_sel}"):
                            entry = {
                                "titulo": row["titulo"],
                                "meal": meal_sel,
                                "comensales": int(row["comensales"]),
                                "ingredientes": row["ingredientes"],
                            }
                            if day_sel not in st.session_state.planner:
                                st.session_state.planner[day_sel] = []
                            st.session_state.planner[day_sel].append(entry)
                            save_planner(st.session_state.planner)
                            st.rerun()

    # ── Weekly grid ───────────────────────────────────────────────────────────
    cols = st.columns(7)
    for i, dia in enumerate(DIAS):
        with cols[i]:
            st.markdown(f'<div class="day-header">{dia[:3]}</div>', unsafe_allow_html=True)
            entries = st.session_state.planner.get(dia, [])
            if not entries:
                st.markdown('<div class="day-box"><span style="color:#aaa;font-size:0.75rem">Vacío</span></div>', unsafe_allow_html=True)
            else:
                box_html = '<div class="day-box">'
                for entry in entries:
                    icon = entry["meal"].split()[0]
                    box_html += f'<div class="planned-recipe">{icon} {entry["titulo"][:22]}…</div>'
                box_html += "</div>"
                st.markdown(box_html, unsafe_allow_html=True)
                # Remove buttons
                for j, entry in enumerate(entries):
                    if st.button("✕", key=f"rm_{dia}_{j}", help=f"Quitar {entry['titulo']}"):
                        st.session_state.planner[dia].pop(j)
                        save_planner(st.session_state.planner)
                        st.rerun()

    # ── Planner summary ───────────────────────────────────────────────────────
    total_recipes = sum(len(v) for v in st.session_state.planner.values())
    if total_recipes:
        st.markdown(f"**{total_recipes} recetas** planificadas esta semana")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EXPLORAR
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("🔍 Explorar Recetas")

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.expander("🎛️ Filtros", expanded=True):
        f1, f2, f3 = st.columns(3)
        with f1:
            search_text = st.text_input("🔎 Buscar por nombre", placeholder="paella, tortilla…")
            categorias = ["Todas"] + sorted(df["categoria"].unique().tolist())
            cat_sel = st.selectbox("Categoría", categorias)
        with f2:
            ing_search = st.text_input("🥕 Filtrar por ingrediente", placeholder="pollo, tomate…")
            dificultades = ["Todas"] + sorted(df["dificultad"].unique().tolist())
            dif_sel = st.selectbox("Dificultad", dificultades)
        with f3:
            max_time = st.select_slider(
                "⏱️ Tiempo máximo",
                options=[15, 30, 45, 60, 90, 120, 999],
                value=999,
                format_func=lambda x: "Sin límite" if x == 999 else f"{x} min"
            )
            min_rating = st.slider("⭐ Valoración mínima", 0.0, 5.0, 0.0, 0.5)

    # ── Apply filters ─────────────────────────────────────────────────────────
    filtered = df.copy()

    if search_text:
        filtered = filtered[filtered["titulo"].str.contains(search_text, case=False, na=False)]

    if cat_sel != "Todas":
        filtered = filtered[filtered["categoria"] == cat_sel]

    if dif_sel != "Todas":
        filtered = filtered[filtered["dificultad"] == dif_sel]

    if ing_search.strip():
        search_lower = ing_search.strip().lower()
        filtered = filtered[
            filtered["_ing_tokens"].apply(
                lambda tokens: any(search_lower in t for t in tokens)
            )
        ]

    if max_time < 999:
        filtered = filtered[
            filtered["tiempo_total"].apply(time_to_minutes) <= max_time
        ]

    if min_rating > 0:
        filtered = filtered[filtered["valoracion_media"] >= min_rating]

    st.caption(f"**{len(filtered):,}** recetas encontradas")

    # ── Results ───────────────────────────────────────────────────────────────
    if filtered.empty:
        st.info("No hay recetas con esos filtros. Prueba a ampliar la búsqueda.")
    else:
        # Sort
        sort_col = st.selectbox("Ordenar por", ["Valoración ↓", "Tiempo ↑", "Nombre A-Z", "Calorías ↑"], key="sort")
        if sort_col == "Valoración ↓":
            filtered = filtered.sort_values("valoracion_media", ascending=False)
        elif sort_col == "Tiempo ↑":
            filtered["_mins"] = filtered["tiempo_total"].apply(time_to_minutes)
            filtered = filtered.sort_values("_mins")
        elif sort_col == "Nombre A-Z":
            filtered = filtered.sort_values("titulo")
        elif sort_col == "Calorías ↑":
            filtered = filtered.sort_values("calorias")

        page_size = 12
        total_pages = max(1, (len(filtered) - 1) // page_size + 1)
        if "exp_page" not in st.session_state:
            st.session_state.exp_page = 1
        # Reset page on filter change
        page = st.session_state.exp_page
        page = min(page, total_pages)

        start = (page - 1) * page_size
        page_df = filtered.iloc[start : start + page_size]

        # Display cards in 2 cols
        card_cols = st.columns(2)
        for idx, (_, row) in enumerate(page_df.iterrows()):
            with card_cols[idx % 2]:
                with st.container():
                    img_col, txt_col = st.columns([1, 2])
                    with img_col:
                        if row["imagen_url"]:
                            st.image(row["imagen_url"], use_container_width=True)
                    with txt_col:
                        st.markdown(f"**{row['titulo']}**")
                        st.markdown(
                            f'<span class="recipe-badge">{row["categoria"]}</span>'
                            f'<span class="recipe-badge">⏱ {row["tiempo_total"]}</span>'
                            f'<span class="recipe-badge">{row["dificultad"].replace("Dificultad ", "")}</span>',
                            unsafe_allow_html=True
                        )
                        if row["valoracion_media"] > 0:
                            st.markdown(
                                f'<span class="stars">{star_display(row["valoracion_media"])}</span> '
                                f'<span style="font-size:0.75rem;color:#666">{row["valoracion_media"]:.1f}</span>',
                                unsafe_allow_html=True
                            )
                        if row["calorias"] > 0:
                            st.caption(f"🔥 {row['calorias']:.0f} kcal · 👥 {row['comensales']} pers.")

                    with st.expander("Ver ingredientes y pasos"):
                        ings = parse_ingredients_display(row["ingredientes"])
                        if ings:
                            st.markdown("**Ingredientes:**")
                            for ing in ings:
                                st.markdown(f"- {ing}")
                        if pd.notna(row.get("pasos")) and row["pasos"]:
                            st.markdown("**Preparación:**")
                            steps = str(row["pasos"]).split(" | ")
                            for s in steps[:5]:
                                if s.strip():
                                    st.markdown(f"{s.strip()}")
                            if len(steps) > 5:
                                st.caption(f"… y {len(steps)-5} pasos más")
                        if row["url"]:
                            st.markdown(f"[Ver receta completa →]({row['url']})")

                        # Quick-add to planner from here
                        st.markdown("**Añadir al planner:**")
                        qd, qm, qb = st.columns([2, 2, 1])
                        with qd:
                            qday = st.selectbox("", DIAS, key=f"qday_{row.name}")
                        with qm:
                            qmeal = st.selectbox("", MEAL_SLOTS, key=f"qmeal_{row.name}")
                        with qb:
                            if st.button("➕", key=f"qadd_{row.name}"):
                                entry = {
                                    "titulo": row["titulo"],
                                    "meal": qmeal,
                                    "comensales": int(row["comensales"]),
                                    "ingredientes": row["ingredientes"],
                                }
                                if qday not in st.session_state.planner:
                                    st.session_state.planner[qday] = []
                                st.session_state.planner[qday].append(entry)
                                save_planner(st.session_state.planner)
                                st.success("✓ Añadida al planner")

                st.markdown("---")

        # Pagination
        p1, p2, p3 = st.columns([1, 3, 1])
        with p1:
            if st.button("◀ Anterior") and page > 1:
                st.session_state.exp_page = page - 1
                st.rerun()
        with p2:
            st.caption(f"Página {page} de {total_pages}")
        with p3:
            if st.button("Siguiente ▶") and page < total_pages:
                st.session_state.exp_page = page + 1
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — LISTA DE LA COMPRA
# ═══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🛒 Lista de la Compra")

    planned_entries = [
        entry
        for entries in st.session_state.planner.values()
        for entry in entries
    ]

    if not planned_entries:
        st.info("Añade recetas al planner primero para generar la lista de la compra.")
    else:
        st.caption(f"Basado en **{len(planned_entries)} recetas** planificadas")

        # ── Parse and aggregate ingredients ───────────────────────────────────
        # Collect all raw ingredient strings
        all_ingredients_raw = []
        for entry in planned_entries:
            ings = parse_ingredients_display(entry.get("ingredientes", ""))
            all_ingredients_raw.extend(ings)

        # Aggregate duplicates (simple text match)
        from collections import Counter
        # Normalize for grouping
        def normalize_ing(s):
            s = s.lower().strip()
            s = re.sub(r"\s+", " ", s)
            return s

        normalized = [normalize_ing(i) for i in all_ingredients_raw]
        counts = Counter(normalized)

        # ── Categorize ingredients ─────────────────────────────────────────────
        CATEGORIES = {
            "🥩 Carnes y proteínas": [
                "pollo", "ternera", "cerdo", "carne", "pechuga", "muslo", "bistec",
                "tocino", "bacon", "jamón", "chorizo", "salchicha", "atún", "salmón",
                "merluza", "bacalao", "gambas", "camarones", "huevo"
            ],
            "🥦 Verduras y hortalizas": [
                "cebolla", "tomate", "ajo", "pimiento", "zanahoria", "calabacín",
                "patata", "lechuga", "espinaca", "acelga", "champiñon", "berenjena",
                "puerro", "apio", "pepino", "coliflor", "brócoli", "aguacate",
                "maíz", "judía", "guisante"
            ],
            "🍋 Frutas": [
                "limón", "naranja", "manzana", "plátano", "fresa", "mango", "piña",
                "uva", "kiwi", "melocotón", "pera", "ciruela"
            ],
            "🥛 Lácteos": [
                "leche", "nata", "mantequilla", "queso", "yogur", "crema", "feta",
                "mozzarella", "parmesano"
            ],
            "🌾 Harinas, cereales y legumbres": [
                "harina", "arroz", "pasta", "macarrón", "espagueti", "pan", "avena",
                "lenteja", "garbanzo", "frijol", "alubia"
            ],
            "🫙 Aceites, salsas y condimentos": [
                "aceite", "vinagre", "soja", "mayonesa", "ketchup", "salsa", "caldo",
                "vino", "agua"
            ],
            "🧂 Especias y hierbas": [
                "sal", "pimienta", "orégano", "tomillo", "romero", "laurel", "comino",
                "pimentón", "curry", "canela", "perejil", "cilantro", "albahaca",
                "azafrán", "nuez moscada"
            ],
            "🍬 Otros": []
        }

        def categorize(ing: str) -> str:
            ing_lower = ing.lower()
            for cat, keywords in CATEGORIES.items():
                if any(kw in ing_lower for kw in keywords):
                    return cat
            return "🍬 Otros"

        # Group by category
        by_category = {}
        for ing, count in sorted(counts.items()):
            cat = categorize(ing)
            by_category.setdefault(cat, []).append((ing, count))

        # ── Controls ──────────────────────────────────────────────────────────
        c1, c2 = st.columns([3, 1])
        with c2:
            # Export as text
            export_lines = ["LISTA DE LA COMPRA\n" + "="*30]
            for cat, items in by_category.items():
                export_lines.append(f"\n{cat}")
                for ing, cnt in items:
                    prefix = f"({cnt}x) " if cnt > 1 else ""
                    export_lines.append(f"  ☐ {prefix}{ing}")
            export_text = "\n".join(export_lines)
            st.download_button(
                "📥 Exportar .txt",
                export_text,
                file_name="lista_compra.txt",
                mime="text/plain",
                use_container_width=True
            )

        # ── Display ───────────────────────────────────────────────────────────
        if "checked_items" not in st.session_state:
            st.session_state.checked_items = set()

        all_items_flat = [(ing, cnt, cat) for cat, items in by_category.items() for ing, cnt in items]
        total_items = len(all_items_flat)
        checked_count = len(st.session_state.checked_items)

        st.progress(checked_count / total_items if total_items else 0,
                    text=f"Completado: {checked_count}/{total_items} artículos")

        if st.button("↺ Desmarcar todo"):
            st.session_state.checked_items = set()
            st.rerun()

        for cat, items in by_category.items():
            if not items:
                continue
            st.markdown(f'<div class="shop-category">{cat}</div>', unsafe_allow_html=True)
            for ing, cnt in items:
                label = f"~~{ing}~~" if ing in st.session_state.checked_items else ing
                prefix = f"({cnt}x) " if cnt > 1 else ""
                checked = st.checkbox(
                    f"{prefix}{ing}",
                    value=ing in st.session_state.checked_items,
                    key=f"chk_{ing[:40]}"
                )
                if checked:
                    st.session_state.checked_items.add(ing)
                else:
                    st.session_state.checked_items.discard(ing)




# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — IA (Groq — gratuito)
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🤖 Sugerencias con IA")
    st.caption("Powered by **Groq** (gratuito) · Modelo Llama 3.3 70B")

    # Try secrets first, then manual input
    try:
        groq_key_default = st.secrets.get("GROQ_API_KEY", "")
    except Exception:
        groq_key_default = ""

    if groq_key_default:
        api_key = groq_key_default
    else:
        api_key = st.text_input(
            "API Key de Groq",
            type="password",
            help="Gratis en console.groq.com → API Keys · No se almacena"
        )

    if not api_key:
        st.info(
            "**¿Cómo obtener tu API key gratuita?**\n\n"
            "1. Ve a [console.groq.com](https://console.groq.com) y crea una cuenta (gratis)\n"
            "2. Menú lateral → **API Keys** → **Create API Key**\n"
            "3. Pégala en el campo de arriba\n\n"
            "Para no introducirla cada vez, crea `.streamlit/secrets.toml` con:\n"
            "```\nGROQ_API_KEY = 'gsk_...'\n```"
        )

    mode = st.radio("¿Qué quieres hacer?", [
        "🥬 Tengo estos ingredientes, ¿qué cocino?",
        "📅 Generar menú semanal equilibrado",
        "🔄 Sustituir un ingrediente",
    ], horizontal=False)

    if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
        user_input = st.text_area(
            "¿Qué tienes en casa?",
            placeholder="ej: pollo, patatas, cebolla, tomate, ajo…",
            height=80
        )
        extra = st.text_input(
            "Restricciones o preferencias (opcional)",
            placeholder="vegetariano, sin gluten, menos de 30 minutos…"
        )
    elif mode == "📅 Generar menú semanal equilibrado":
        user_input = ""
        extra = st.text_area(
            "Preferencias / restricciones",
            placeholder="4 personas, sin pescado, variado, mediterráneo…",
            height=80
        )
    else:
        user_input = st.text_input(
            "Ingrediente que quieres sustituir",
            placeholder="ej: nata líquida"
        )
        extra = st.text_input(
            "Contexto de la receta",
            placeholder="ej: salsa carbonara, sin lactosa"
        )

    if st.button("✨ Preguntar a la IA", type="primary", disabled=not api_key):

        # ── Helper: buscar recetas reales en el dataset ────────────────────────
        def buscar_recetas_dataset(keywords: list[str], max_results: int = 30) -> pd.DataFrame:
            """Devuelve recetas del dataset que contienen alguna de las palabras clave."""
            if not keywords:
                return df.sample(min(max_results, len(df)))
            mask = pd.Series([False] * len(df), index=df.index)
            for kw in keywords:
                kw = kw.strip().lower()
                if len(kw) < 2:
                    continue
                mask |= df["_ing_tokens"].apply(lambda tokens: any(kw in t for t in tokens))
                mask |= df["titulo"].str.lower().str.contains(kw, na=False)
            resultado = df[mask]
            if resultado.empty:
                resultado = df.sample(min(max_results, len(df)))
            return resultado.head(max_results)

        def recetas_a_texto(subset: pd.DataFrame, max_r: int = 20) -> str:
            """Serializa recetas del dataset en texto compacto para el prompt."""
            lines = []
            for _, row in subset.head(max_r).iterrows():
                ings = row["ingredientes"][:200] if row["ingredientes"] else "N/D"
                lines.append(
                    f"- {row['titulo']} | {row['categoria']} | {row['tiempo_total']} | "
                    f"Ingredientes: {ings}"
                )
            return "\n".join(lines)

        # ── Construir prompt con datos reales ──────────────────────────────────
        if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?":
            keywords = [w.strip() for w in user_input.replace(",", " ").split() if len(w.strip()) > 2]
            candidatas = buscar_recetas_dataset(keywords, max_results=40)
            recetas_txt = recetas_a_texto(candidatas, max_r=25)
            prompt = (
                "Eres un asistente de cocina. Tu única fuente de recetas es la siguiente lista "
                "extraída de un dataset real. NO inventes recetas que no estén en esta lista.\n\n"
                f"RECETAS DISPONIBLES EN EL DATASET:\n{recetas_txt}\n\n"
                f"El usuario tiene estos ingredientes: {user_input}.\n"
                f"Restricciones o preferencias: {extra or 'ninguna'}.\n\n"
                "Selecciona de la lista de arriba las 5 recetas que mejor encajen con los "
                "ingredientes del usuario. Para cada una indica:\n"
                "- Nombre exacto (tal como aparece en la lista)\n"
                "- Por qué encaja con lo que tiene\n"
                "- Qué ingredientes adicionales necesitaría (si alguno)\n"
                "- Tiempo de preparación\n\n"
                "Si ninguna receta encaja bien, dilo claramente y sugiere las más cercanas.\n"
                "Responde en español."
            )

        elif mode == "📅 Generar menú semanal equilibrado":
            # Muestra variada del dataset por categoría
            muestra = df.groupby("categoria", group_keys=False).apply(
                lambda g: g.sample(min(5, len(g)))
            ).reset_index(drop=True)
            recetas_txt = recetas_a_texto(muestra, max_r=50)
            prompt = (
                "Eres un nutricionista y chef. Tu única fuente de recetas es la siguiente lista "
                "extraída de un dataset real. NO inventes recetas que no estén en esta lista.\n\n"
                f"RECETAS DISPONIBLES EN EL DATASET:\n{recetas_txt}\n\n"
                f"Preferencias o restricciones del usuario: {extra or 'ninguna'}.\n\n"
                "Diseña un menú semanal completo (lunes a domingo, comida y cena) usando "
                "ÚNICAMENTE recetas de la lista de arriba. Asegúrate de que sea variado "
                "y equilibrado entre categorías.\n"
                "Formato: lista por día con el nombre exacto de cada receta.\n"
                "Al final añade una nota breve sobre el equilibrio nutricional de la semana.\n"
                "Responde en español."
            )

        else:  # Sustituir ingrediente — aquí sí puede usar conocimiento general
            prompt = (
                "Eres un chef experto.\n"
                f"El usuario quiere sustituir '{user_input}' en: {extra or 'una receta'}.\n\n"
                "Sugiere 3 sustitutos posibles indicando para cada uno:\n"
                "- Qué es el sustituto\n"
                "- Cómo afecta al sabor y textura\n"
                "- En qué proporción usarlo\n\n"
                "Responde en español, de forma práctica y concisa."
            )

        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            with st.spinner("Buscando en tu dataset y consultando a la IA…"):
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1200,
                    temperature=0.3,  # Más bajo = más fiel al contexto dado
                )
            st.markdown("### 💬 Respuesta")
            st.markdown(response.choices[0].message.content)

            # Mostrar cuántas recetas se pasaron como contexto
            if mode != "🔄 Sustituir un ingrediente":
                n = len(candidatas) if mode == "🥬 Tengo estos ingredientes, ¿qué cocino?" else len(muestra)
                st.caption(f"🔍 La IA analizó {n} recetas reales de tu dataset para esta respuesta.")

        except ImportError:
            st.error("Instala el cliente: `pip install groq`")
        except Exception as e:
            st.error(f"Error con la API de Groq: {e}")

    st.markdown("---")
    st.caption(
        "Tu API key no se almacena nunca. "
        "Para uso frecuente guárdala en `.streamlit/secrets.toml` como `GROQ_API_KEY = 'gsk_...'`"
    )
