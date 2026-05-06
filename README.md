# 🍽️ Planificador de Recetas

App Streamlit para explorar tu dataset de recetas, planificar menús semanales y generar la lista de la compra.

## Instalación local (5 minutos)

```bash
# 1. Crea un entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 2. Instala dependencias
pip install -r requirements.txt

# 3. Coloca tu dataset
# Copia tu archivo Excel como:  dataset.xlsx  (en esta carpeta)

# 4. Lanza la app
streamlit run app.py
```

La app se abrirá en http://localhost:8501

---

## Despliegue en la nube (gratis, acceso desde móvil)

1. **Crea cuenta** en [streamlit.io/cloud](https://streamlit.io/cloud) (gratis)
2. **Sube el código** a un repositorio GitHub:
   ```bash
   git init
   git add app.py requirements.txt README.md
   git commit -m "Planificador de recetas"
   git branch -M main
   git remote add origin https://github.com/TU_USUARIO/recetas-app.git
   git push -u origin main
   ```
3. En Streamlit Cloud → **New app** → selecciona el repo → Deploy
4. Para el dataset: usa el **uploader** dentro de la app o configura un secreto con la ruta

> ⚠️ El dataset no se sube a GitHub si es privado. Usa el uploader lateral de la app.

---

## Estructura de la app

| Pestaña | Funcionalidad |
|---------|--------------|
| 📅 Planner | Planificador semanal (desayuno / comida / cena) |
| 🔍 Explorar | Filtros por categoría, ingrediente, dificultad, tiempo, valoración |
| 🛒 Compra | Lista de la compra automática con checkboxes y exportación .txt |
| 🤖 IA | Sugerencias Claude: qué cocino / menú semanal / sustituciones |

---

## Uso de la IA (opcional)

La pestaña IA usa la API de Anthropic. Necesitas una API key de [console.anthropic.com](https://console.anthropic.com).

Para no tener que introducirla cada vez, crea el archivo `.streamlit/secrets.toml`:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
```

---

## Formato del dataset esperado

El archivo Excel debe tener estas columnas (las mismas que el ejemplo):

| Columna | Descripción |
|---------|-------------|
| `titulo` | Nombre de la receta |
| `categoria` | Categoría principal |
| `ingredientes` | Ingredientes separados por ` \| ` |
| `tiempo_total` | Tiempo (ej: `45m`, `1h 30m`) |
| `dificultad` | Nivel de dificultad |
| `comensales` | Número de personas |
| `valoracion_media` | Nota media (0-5) |
| `imagen_url` | URL de imagen (opcional) |
| `url` | URL de la receta original (opcional) |
