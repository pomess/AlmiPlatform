# Disease360 — Guion de Demo
**Formato de grabacion:** Loom con narracion en pantalla
**Duracion objetivo:** 3–4 minutos
**Tono:** Seguro, ritmo rapido, sin relleno — mostrar, no explicar.

---

## APERTURA (10 segundos)

**[Pantalla: Landing page en localhost:5173]**

> "Esto es Disease360 — una plataforma de inteligencia competitiva construida para Almirall. Un solo espacio de trabajo. Todos los competidores. Todos los farmacos. Todos los ensayos. Os enseno lo que hace."

**Click en "Open platform" → entra al cockpit.**

---

## ACTO 1: EL DASHBOARD (60–70 segundos)

**[Pantalla: Dashboard — mapa global, 16 pins de competidores visibles]**

> "El dashboard es el centro de mando en vivo. Dieciseis sedes de competidores monitorizadas en toda Espana — Barcelona, Madrid, Tres Cantos. Cada una es una farmaceutica con programas de dermatologia en suelo espanol."

**Click en el pin de Roche (Sant Cugat).**

> "Haz click en cualquier pin y obtienes tres cosas a la vez: un holograma 3D de su sede real, una ficha con sus areas terapeuticas, y un feed de noticias sacado de la prensa farma de esta manana."

**[El holograma se renderiza, la ficha aparece, el panel de noticias se muestra]**

> "El holograma esta construido con datos reales de OpenStreetMap — estas son las estructuras reales del campus de Roche en Sant Cugat."

**Ahora demostrar la voz (mantener Espacio):**

> "Y responde por voz. Mirad."

**Mantener Espacio, decir:** "Fly to Sanofi"

> *(La camara vuela al pin de Sanofi en Barcelona, aparecen holograma + noticias)*

> "Pregunta por cualquier competidor y el mapa se mueve hacia el. El agente entiende contexto farma — companias, ubicaciones, indicaciones."

**Mantener Espacio, decir:** "What's the latest on AstraZeneca?"

> *(El mapa vuela a AstraZeneca, el panel de noticias muestra titulares relevantes)*

---

## ACTO 2: EL BULLSEYE (50–60 segundos)

**Click en "Bullseye" en la navegacion superior.**

**[Pantalla: Visualizacion Bullseye — anillos concentricos con puntos de farmacos]**

> "Esto es el paisaje competitivo como un radar. Cinco anillos concentricos — desde Aprobado en el centro, pasando por Fase III, Fase II, Fase I, hasta Preclinico en el borde."

> "Cada punto es un farmaco. Las companias se distribuyen alrededor del perimetro. De un vistazo ves quien esta donde — Sanofi y Lilly dominando late-stage, el Ebglyss de Almirall en el anillo de Aprobados con ese halo azul marino."

**Click en un punto (p.ej. dupilumab o un activo de Almirall).**

> "Haz click en cualquier activo y obtienes el dossier completo — diana, modalidad, via de administracion, timeline de desarrollo, fase mas alta. Todo curado de fuentes primarias."

**Navegar entre indicaciones si hay multiples pestanas:**

> "Tres indicaciones conectadas hoy: dermatitis atopica, hidradenitis supurativa y psoriasis. Misma interfaz, mismo drill-down. Anadir una indicacion es anadir un dataset — no una herramienta nueva."

---

## ACTO 3: EL CHAT + GRAFO DE CONOCIMIENTO (50–60 segundos)

**Click en "Chat" en la navegacion superior.**

**[Pantalla: Interfaz de chat con selector de brain]**

> "El chat esta respaldado por un grafo de conocimiento — no solo un LLM. Debajo hay un vault curado con ensayos clinicos, evidencia de PubMed e inteligencia competitiva."

**Escribir o decir:** "What clinical trials are recruiting for hidradenitis suppurativa right now?"

> *(El agente responde con datos estructurados del BioMCP Brain — IDs de ensayos, estados, farmacos involucrados)*

> "Esa respuesta no viene de un modelo generico. Viene de 33 registros de ClinicalTrials.gov y 3 papers de PubMed que ingestamos, estructuramos y enlazamos. El agente cita sus fuentes — cada dato es trazable."

**Click en "Graph" en la navegacion superior.**

**[Pantalla: Visualizacion del grafo de conocimiento — nodos y aristas]**

> "Y aqui esta el grafo sobre el que se construyen esas respuestas. Farmacos, dianas, mecanismos, companias, indicaciones — todo conectado. Haz click en un nodo y ves cada conexion."

> "Esta es la capa de contexto. Cuando el agente dice 'secukinumab se esta estudiando en 3 ensayos de HS,' es porque puede recorrer este grafo — no porque memorizo un training set."

---

## CIERRE (15 segundos)

**Navegar de vuelta al Dashboard (o Landing).**

> "Una plataforma. Noticias en tiempo real, mapas en vivo, evidencia estructurada, un grafo de conocimiento, y una IA que puede navegar todo esto por voz o texto. Construida para el equipo de franquicia que necesita respuestas ahora — no el proximo trimestre."

> "Esto es Disease360."

---

## CONSEJOS PARA LA GRABACION

- **Resolucion:** 1920x1080, navegador a pantalla completa (F11)
- **Limpiar localStorage** antes de grabar si quieres mostrar el flujo de "carga instantanea desde datos estaticos"
- **Pre-calentar:** Abre el dashboard una vez antes de grabar para que todos los assets esten en cache
- **Voz:** Habla claro al micro cuando hagas push-to-talk. El STT funciona mejor con frases cortas y directas como "Fly to Roche" o "Show me Pfizer"
- **Ritmo:** No corras las transiciones — deja que las animaciones de flyTo y los hologramas terminen antes de hablar encima (tardan ~2s)
- **Si la voz falla:** Usa la caja de texto de abajo ("ASK DISEASE360") como backup — mismo agente, entrada por texto
