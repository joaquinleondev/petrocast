# ADR-0008: Stack del backend (Python + FastAPI)

- **Estado:** Aceptado
- **Fecha:** 2026-04-21
- **Autores:** Equipo Petrocast
- **Decisores:** Equipo Petrocast

## Contexto y problema

La adenda técnica de Fase 1 requiere implementar un mock de servidor
API REST con documentación OpenAPI generada automáticamente. A partir
de Fase 2, el mismo servicio deberá integrarse con el motor de
procesamiento de datos y, en Fase 3, con modelos de Machine Learning
para pronóstico de producción.

La elección del lenguaje y framework del backend condiciona:

- La velocidad de desarrollo del mock en Fase 1.
- La facilidad de integración con librerías de datos y ML en Fases 2-3.
- La generación automática de documentación OpenAPI (requisito explícito
  de la adenda).
- La experiencia del equipo con las tecnologías.

## Drivers de la decisión

- La adenda exige documentación OpenAPI accesible en línea; preferimos
  que sea generada automáticamente desde el código, no mantenida
  manualmente.
- Las Fases 2 y 3 involucran procesamiento de datos (pandas, numpy) y
  modelos de ML (scikit-learn, statsmodels). El ecosistema Python es
  dominante en esas áreas.
- El equipo tiene mayor experiencia en Python que en otros lenguajes
  del lado del servidor.
- El servicio es stateless y de baja carga (mock + pronósticos por
  demanda); no se necesita rendimiento extremo.

## Opciones consideradas

1. **Python + FastAPI**
2. **Python + Flask**
3. **Node.js + Express**
4. **Go + Gin**

## Decisión

Adoptamos **Python + FastAPI**.

FastAPI genera la spec OpenAPI y la UI de Swagger automáticamente a
partir de los type hints y modelos Pydantic del código, sin
configuración adicional. Esto satisface directamente el requisito de
la adenda de tener la documentación "accesible en línea".

Además, al usar Python en el backend, las Fases 2 y 3 pueden importar
las mismas librerías de datos y ML directamente, sin necesidad de
una capa de comunicación inter-proceso o inter-lenguaje.

## Consecuencias

**Positivas:**

- OpenAPI/Swagger disponible en `/docs` sin configuración extra.
- Validación automática de requests y responses vía Pydantic.
- Reutilización directa de librerías de datos y ML en fases posteriores.
- Tipado estático con type hints mejora la legibilidad y el soporte del IDE.
- Alta velocidad de desarrollo: decoradores declarativos para rutas,
  modelos y validaciones.

**Negativas / trade-offs asumidos:**

- Python tiene mayor uso de memoria y menor throughput que Go o Node.js
  en cargas altas. No es relevante para el volumen esperado del TP.
- FastAPI requiere Python ≥ 3.8; el proyecto usa 3.12, sin problemas.

**Neutras:**

- ASGI (uvicorn) en lugar de WSGI (gunicorn). Adecuado para FastAPI y
  sin impacto práctico para el caso de uso actual.

## Pros y contras de cada opción

### Python + FastAPI (elegida)

- ✅ Genera OpenAPI automáticamente desde el código.
- ✅ Validación de tipos con Pydantic integrada.
- ✅ Mismo lenguaje que el ecosistema de datos/ML de Fases 2-3.
- ✅ Experiencia del equipo en Python.
- ❌ Menor rendimiento que Go para cargas altas (irrelevante a esta escala).

### Python + Flask

- ✅ Más simple y liviano que FastAPI.
- ✅ Mismo ecosistema Python para Fases 2-3.
- ❌ No genera OpenAPI automáticamente; requiere extensiones adicionales
  (flask-smorest, apispec) con mayor configuración.
- ❌ Sin validación de tipos nativa; requiere marshmallow u otros.

### Node.js + Express

- ✅ Ecosistema maduro, muy usado para APIs REST.
- ❌ Lenguaje diferente al ecosistema de datos/ML (Python); introduciría
  fricción en Fases 2-3.
- ❌ OpenAPI requiere librerías externas (swagger-jsdoc, etc.).
- ❌ El equipo tiene menos experiencia en Node.js.

### Go + Gin

- ✅ Rendimiento excelente, binario compilado liviano.
- ❌ Curva de aprendizaje alta para el equipo.
- ❌ Ecosistema de ML inexistente; Fases 2-3 requerirían comunicación
  entre servicios (complejidad innecesaria).
- ❌ OpenAPI requiere anotaciones manuales o generación externa.

## Referencias

- [FastAPI — documentación oficial](https://fastapi.tiangolo.com/)
- [Pydantic v2](https://docs.pydantic.dev/)
- Adenda técnica Fase 1 (`docs/prd/adenda-fase-1.md`) — requisito de
  documentación OpenAPI accesible en línea.
- ADR-0007 — contrato OpenAPI de Fase 1.
