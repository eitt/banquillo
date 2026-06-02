# 📋 Banquillo · Sistema de Optimización y Agenda de Orientadores

Banquillo es una herramienta inteligente de agendamiento y optimización de horarios diseñada para coordinar las agendas de orientadores en diferentes comunidades o barrios (con enfoque principal en la comunidad de **La Cumbre**).

El sistema utiliza un **Algoritmo Genético** avanzado para resolver asignaciones complejas de personal basándose en disponibilidades, horas máximas permitidas y evitando traslapes de horario.

---

## 🚀 Características Clave

1. **Dashboard Interactivo**: Desarrollado en **Streamlit** con una estética oscura premium, visualización de métricas en tiempo real, gráficos de horas asignadas y ocupación diaria.
2. **Algoritmo Genético de Optimización**: Optimiza asignaciones respetando de forma inteligente restricciones duras y blandas.
3. **Persistencia SQL**: Uso de una base de datos SQLite para almacenar orientadores, disponibilidades de horarios, turnos requeridos, asignaciones finales y el estado de las citas de los usuarios.
4. **Integración con Excel**:
   - **Importación**: Permite cargar las agendas y orientadores directamente desde archivos Excel.
   - **Exportación Estética**: Genera reportes listos para compartir en Excel con un diseño corporativo limpio, autoajuste de columnas y colores corporativos profesionales.
5. **Pipeline de Consola (CLI)**: Permite la ejecución automatizada de todo el proceso de importación, optimización y exportación de extremo a extremo sin necesidad de usar la interfaz web.

---

## 📁 Estructura del Proyecto

*   `app.py`: La interfaz gráfica de usuario y panel de control web construida sobre Streamlit.
*   `db_manager.py`: Controlador del modelo de datos. Gestiona la base de datos SQLite, las sentencias SQL, y la importación/exportación a Excel.
*   `scheduler_opt.py`: El motor del algoritmo genético que calcula y asigna los horarios más óptimos.
*   `pipeline.py`: Script de automatización de comandos CLI para integrar el flujo de datos.
*   `requirements.txt`: Lista de dependencias de Python necesarias.

---

## 🛠️ Instalación y Requisitos

Asegúrate de tener Python 3.8 o superior instalado en tu sistema.

1.  **Clonar el repositorio o situarse en el directorio:**
    ```bash
    cd Banquillo
    ```

2.  **Crear un entorno virtual (recomendado):**
    ```bash
    python -m venv venv
    ```

3.  **Activar el entorno virtual:**
    *   En Windows:
        ```bash
        venv\Scripts\activate
        ```
    *   En macOS/Linux:
        ```bash
        source venv/bin/activate
        ```

4.  **Instalar las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

---

## ⚙️ Uso del Pipeline CLI (Consola)

El pipeline de consola permite procesar archivos, ejecutar el optimizador y guardar resultados de manera automática en un solo paso:

```bash
python pipeline.py --start-date "2025-12-01" --end-date "2025-12-31" --barrio "La Cumbre"
```

### Argumentos del CLI

*   `--import-path`: Ruta del archivo Excel de origen para importar (por defecto: `AGENDAS - LA CUMBRE.xlsx`).
*   `--export-path`: Ruta del archivo Excel final a generar (por defecto: `AGENDAS_EXPORTED.xlsx`).
*   `--barrio`: Nombre de la comunidad/barrio a optimizar (por defecto: `La Cumbre`).
*   `--start-date`: Fecha de inicio del periodo a optimizar en formato `YYYY-MM-DD` (por defecto: inicio del mes en curso).
*   `--end-date`: Fecha de fin del periodo a optimizar en formato `YYYY-MM-DD` (por defecto: fin del mes en curso).
*   `--pop-size`: Tamaño de la población del algoritmo genético (por defecto: `100`).
*   `--generations`: Número de generaciones del algoritmo (por defecto: `200`).
*   `--mut-rate`: Tasa de mutación del algoritmo genético (por defecto: `0.15`).
*   `--no-import`: Omitir la fase de importación y utilizar los datos que ya están en la base de datos actual.

---

## 📊 Ejecución del Dashboard Web

Para lanzar la aplicación interactiva de Streamlit, ejecuta el siguiente comando:

```bash
streamlit run app.py
```

Esto abrirá la aplicación en tu navegador web (usualmente en `http://localhost:8501`). A través de esta interfaz puedes:
*   Visualizar métricas clave de la base de datos en tiempo real.
*   Dar de alta, editar y borrar orientadores.
*   Gestionar disponibilidades semanales.
*   Modificar estados de las citas ("libre", "reservada", "asistió", "no asistió").
*   Ejecutar la optimización con sliders interactivos de parámetros.
*   Cargar y descargar los archivos Excel directamente desde la interfaz.

---

## 🧬 Lógica del Algoritmo Genético

El optimizador formula las asignaciones de horarios como un problema de optimización basado en restricciones. La asignación final busca minimizar la **función de penalización (Fitness)** (menor puntaje = mejor horario):

### Restricciones Duras (Altamente Penalizadas)
*   **Disponibilidad (H1)**: Un orientador solo puede ser asignado a un turno si tiene disponibilidad declarada en ese día y rango de horas. (Penalización: `+10000`)
*   **Traslape (H2)**: Un orientador no puede estar asignado a más de un turno que coincida en el mismo horario y fecha. (Penalización: `+10000`)
*   **Límite de Horas Semanales (H3)**: No superar el número máximo de horas configuradas por orientador por semana (por ejemplo, 40h). (Penalización: `+5000` por cada hora excedida)
*   **Turnos Vacíos (H4)**: Intentar cubrir la mayor cantidad posible de turnos requeridos por la comunidad. (Penalización: `+1000` por cada slot vacío)

### Restricciones Blandas (Baja Penalización)
*   **Balance de Carga de Trabajo (S1)**: Distribuye equitativamente las horas asignadas entre todos los orientadores activos, reduciendo la desviación estándar en la carga total de horas. (Penalización variable basada en la desviación estándar)
