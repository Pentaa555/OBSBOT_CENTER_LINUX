# Extraer el QSS y los recursos Qt del ejecutable de OBSBOT Center

Notas de investigación para continuar la extracción del tema/estilos reales
(QSS) y de los recursos de UI (iconos PNG/SVG) embebidos dentro del binario
`OBSBOT_Main.exe` de OBSBOT Center (Windows), para reutilizarlos en esta app
Linux.

> Estado: el QSS **crudo ya se puede extraer** (texto plano en el binario).
> Lo que falta terminar es extraer los **recursos Qt con sus nombres/rutas
> correctos** (los `url(:/...)` que usan los bloques QSS), para lo que la vía
> fiable es la herramienta `qtextract` (Rust) o `qrc2zip` (Go).

---

## 1. Ubicación de los binarios

En el equipo actual la app de Windows fue extraída a:

```
/home/ipuc/Descargas/obsbot_extraido/
├── app/
│   ├── bin/
│   │   ├── OBSBOT_Main.exe     (~92 MB)  <-- la mayoría del QSS y recursos
│   │   ├── OBSBOT_Center.exe   (~14 MB)  <-- QSS adicional
│   │   ├── Qt6*.dll, libdev.dll, ...
│   │   └── ...
│   ├── data/
│   │   ├── center/{images,themes,locale,font}/   <-- assets sueltos (ya usados)
│   │   └── ctrl/{images,themes,locale,font}/
│   └── license/  (LGPL-3.0)
└── _embedded/main/_OBSBOT_Main.exe.extracted/    <-- ~1300 PNG gigantes (basura, ignorar)
```

En **otro equipo**: vuelve a descargar/extraer OBSBOT Center para Windows
(instalador `.exe`) y descomprímelo con 7-Zip / innoextract hasta obtener
`app/bin/OBSBOT_Main.exe`.

---

## 2. Lo que YA está hecho (en el repo)

- Iconos sueltos de `app/data/center/images/` copiados a `app/resources/images/`.
- Tema oscuro propio en `app/resources/themes/dark.qss` (no el QSS del exe;
  uno escrito a mano imitando el look, con la paleta real de OBSBOT).
- Fuente Inter (Regular/Medium/SemiBold) en `app/resources/fonts/`.
- Referencias: `app/resources/themes/obsbot-center-dark.reference.qss`
  (el `Dark.qss` de `data/`, que usa el selector propietario `RMTheme` y
  NO es Qt estándar), y `locale-reference/`.

---

## 3. QSS crudo embebido en el .exe (extraíble YA)

El QSS real de la app está como **texto plano** dentro de los binarios.
Extracción con Python (probado y funciona):

```python
import re
for exe in ("OBSBOT_Main.exe", "OBSBOT_Center.exe"):
    data = open(exe, "rb").read()
    chunks = re.findall(rb"[\x09\x0a\x0d\x20-\x7e]{40,}", data)
    qss = [c.decode("latin-1") for c in chunks
           if b"{" in c and b"}" in c and
           any(k in c for k in (b"background-color", b"border-radius",
                                b"QPushButton", b"QWidget", b"::hover"))]
    open(f"/tmp/{exe}.raw_qss.txt", "w").write(
        "\n\n/* ---- CHUNK ---- */\n\n".join(qss))
    print(exe, "->", len(qss), "chunks")
```

Resultado medido:
- `OBSBOT_Main.exe`  -> **328 chunks** (~526 KB de QSS)
- `OBSBOT_Center.exe` -> 100 chunks (~21 KB)

De los 328 chunks de Main: **250 son autónomos** (solo colores/geometría,
reutilizables tal cual) y **78 referencian recursos internos**
(`url(:/btn/images/...)`, `qproperty-icon`) que viven dentro del .exe.

### Paleta real de OBSBOT Center (extraída del QSS)

- Rojo de acento: `#fb0036` = `rgb(251,0,54)` (variante `rgb(230,0,51)`)
- Fondo ventana: `rgb(55,58,60)`
- Texto: `rgb(255,255,255)`; secundario `rgba(255,255,255,102)` (~40% alpha)
- Superficies/paneles: `rgb(45,48,50)`, `rgb(32,34,35)`, `rgb(27,29,31)`,
  `rgb(25,26,27)`
- Bordes/hover: `rgb(64,69,72)`, `rgb(63,67,69)`
- Azul (links/acento 2): `rgba(34,127,255,1)`
- Deshabilitado: `rgb(122,121,122)`

> TODO opcional: ajustar `app/resources/themes/dark.qss` para usar `#fb0036`
> en vez del `#e23b3b` actual, y los grises reales de arriba.

---

## 4. Recursos Qt embebidos (lo que falta terminar)

Los binarios usan el **Qt Resource System** (rcc) embebido. Para reusar los
78 bloques QSS con `url(:/...)` hacen falta esos PNG/SVG con sus **nombres y
rutas** reales. Hay ~1198 PNG embebidos; de ellos ~991 son de UI (<=128x128).

### Datos que YA se localizaron dentro de OBSBOT_Main.exe

Analizando el PE (probado):
- Image base: `0x140000000`
- Secciones: `.text` RVA `0x1000` (raw `0x400`), `.rdata` RVA `0xa80000`
  (raw `0xa7ec00`), `.data` RVA `0x5747000`, etc.
- **Tabla de nombres** (`qt_resource_name`): file offset **`0xd87ee0`**,
  499 entradas. Formato de entrada: `[u16 len][u32 hash][utf16-be name]`.
  Primeras entradas: `btn`, `images`, `btn_click_24x40.png` (nombres de
  carpeta + archivos → confirma que es la tabla correcta).
- **Tabla de datos** (`qt_resource_data`): primer blob en file offset
  **`0xa9c440`**. Cada blob: `[u32 len big-endian][payload]`. Se contaron
  **497 blobs secuenciales** (coincide con 497 archivos + 2 carpetas = 499).
- **Árbol** (`qt_resource_struct`): NO localizado con fiabilidad todavía.
  Un evaluador dio un falso positivo en `0xd87e00` (se solapa con names, es
  inválido). El nodo file en v1/v2 es de 14 bytes:
  `name_off(u32) flags(u16) country(u16) lang(u16) data_off(u32)`
  (data_off en +10). El nodo dir: `name_off(u32) flags(u16)
  child_count(u32) child_first(u32)`. `flags & 0x2` = directorio.
  El nodo raíz suele ser el ÚLTIMO del array.

### Vía recomendada: `qtextract` (Rust) — escaneo AUTOMÁTICO

`qtextract` encuentra solo las llamadas a `qRegisterResourceData` (no hace
falta dar offsets). Es la forma más fiable. Requiere Rust/cargo.

```bash
# En el otro equipo:
sudo apt install -y cargo            # o instalar rustup
git clone --depth 1 https://github.com/axstin/qtextract /tmp/qtextract
cd /tmp/qtextract
cargo build --release
# Escanear y volcar TODOS los chunks de recursos:
./target/release/qtextract /ruta/a/OBSBOT_Main.exe --chunk 0 --output /tmp/obsbot_res
# Si no encuentra chunks automáticamente, usa --scanall, o pásale los offsets:
#   --data data,names,tree,version   (file offsets, hex,hex,hex,dec)
#   ./target/release/qtextract OBSBOT_Main.exe --data a9c440,d87ee0,<TREE>,2 --output /tmp/obsbot_res
# (data=0xa9c440, names=0xd87ee0 ya confirmados; falta TREE y probar version 1/2/3)
```

### Vía alternativa: `qrc2zip` (Go) — ya compilada en este equipo

Requiere los 3 offsets en DECIMAL (data, names, tree) + versión. En este
equipo quedó compilada en `~/go/bin/qrc2zip`. Uso:

```bash
# qrc2zip executable version tree_offset data_offset names_offset
DATA=$((0xa9c440)); NAMES=$((0xd87ee0)); TREE=<decimal del tree real>
~/go/bin/qrc2zip -v -o resources.zip OBSBOT_Main.exe 2 $TREE $DATA $NAMES
```

Falta hallar el TREE correcto (ver método abajo).

---

## 5. Cómo hallar el offset del árbol (TREE) de forma fiable

El árbol es un array contiguo de nodos. Validación fuerte: recorrer `.rdata`
buscando la posición donde una racha larga (~499) de nodos cumpla:
- `name_off` cae EXACTAMENTE en el inicio de un registro de la tabla de
  nombres (no basta con "es un offset conocido"; debe ser inicio de entry),
- para nodos file: `data_off` cae EXACTAMENTE en el inicio de un blob de la
  tabla de datos,
- para nodos dir: `child_first + child_count` no se sale del array,
- deben aparecer las 3 carpetas (`btn`, `images`, `pic`/etc.) como dirs.

Probar tamaños de nodo 14 (v1/v2) y 22 (v3, con `last_modified` u64). La
versión correcta es la que hace que el árbol enlace los 499 nombres con los
497 blobs sin huecos. Empezar el walk desde el nodo raíz (el que ningún otro
nodo referencia como hijo; suele ser el último).

> Recomendación honesta: NO seguir con el parser manual. Usar `qtextract`,
> que resuelve esto automáticamente y ya está pensado para PE x86-64.

---

## 6. Pasos concretos para el otro equipo

1. Obtener `OBSBOT_Main.exe` (extraer el instalador de OBSBOT Center).
2. Instalar Rust: `sudo apt install -y cargo` (o `rustup`).
3. `git clone https://github.com/axstin/qtextract && cargo build --release`.
4. `qtextract OBSBOT_Main.exe --chunk 0 --output /tmp/obsbot_res`
   (si falla el autoscan, `--scanall`, y si aún así, pasar
   `--data a9c440,d87ee0,<TREE>,<ver>`).
5. Revisar `/tmp/obsbot_res`: tendrá el árbol `:/btn/images/*.png`,
   `:/icon/images/*`, `:/pic/images/*`, etc. con nombres reales.
6. Copiar los PNG/SVG relevantes a `app/resources/images/` (o una subcarpeta
   `app/resources/qtres/`), respetando nombres para casar con el QSS.
7. Tomar los 250 bloques QSS autónomos + los 78 con recursos (ya con las
   rutas reapuntadas a `app/resources/...`) y consolidarlos en
   `app/resources/themes/obsbot-extracted.qss`. Aplicarlo o portar los
   estilos útiles a `dark.qss`.
8. Actualizar `THIRD_PARTY_LICENSES.md`: estos recursos son de OBSBOT Center
   (LGPL-3.0). Mantener la atribución.

---

## 7. Snippets Python ya validados (reutilizar)

Parseo de cabeceras PE (image base, secciones, file<->RVA) y localización de
la tabla de nombres/datos: ver el historial de este trabajo. Puntos clave ya
confirmados para `OBSBOT_Main.exe`:

```
image_base   = 0x140000000
names_start  = 0xd87ee0   # qt_resource_name (499 entradas)
data_start   = 0xa9c440   # qt_resource_data (primer blob; 497 blobs)
tree_start   = ???        # qt_resource_struct  <-- PENDIENTE
node_size    = 14 (v1/v2) o 22 (v3)   <-- determinar por validación
```

Entrada de nombre: `[u16 len][u32 hash][utf16-be * len]`.
Blob de datos:     `[u32 len big-endian][payload]`.
Nodo file (v14):   `name_off(u32) flags(u16) country(u16) lang(u16) data_off(u32)`.
Nodo dir  (v14):   `name_off(u32) flags(u16) child_count(u32) child_first(u32)`.

---

## 8. Licencia / cumplimiento

OBSBOT Center se distribuye bajo **LGPL-3.0** (ver `app/license/LICENSE` en
el paquete). Sus iconos/QSS pueden reutilizarse manteniendo la atribución
(ya documentada en `THIRD_PARTY_LICENSES.md`). Las fuentes tienen licencias
propias: Inter es SIL OFL (la que usamos); HarmonyOS Sans es de Huawei
(uso libre con atribución, no redistribuir suelta).
