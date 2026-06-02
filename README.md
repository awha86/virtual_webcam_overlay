# Webcam Overlay for Teams

Tilføjer et dynamisk tekst-overlay til dit webcam og eksponerer det som en virtuel kamera-enhed, som Teams (og andre apps) kan bruge.

## Arkitektur

```
Dit webcam → OpenCV → overlay (Pillow) → pyvirtualcam → Unity Capture driver
                                                              ↓
                                                    Teams vælger "Unity Video Capture"

POST localhost:5123/overlay  ← opdaterer teksten live
```

## Installation (Windows)

### 1. Unity Capture-driver

Driveren skaber den virtuelle kamera-enhed i Windows.

1. Download seneste release fra: https://github.com/schellingb/UnityCapture/releases
2. Pak zip-filen ud
3. Åbn **PowerShell som Administrator**
4. Kør:
   ```powershell
   cd <sti-til-udpakket-mappe>\Install
   regsvr32 /s UnityCaptureFilter64bit.dll
   ```
5. Verificér: åbn Teams → Indstillinger → Enheder → Kamera → du bør se **"Unity Video Capture"**

### 2. Python-afhængigheder

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Brug

### Start

```powershell
python overlay.py
```

Outputtet viser:

```
[API]  http://localhost:5123
[CAM]  Webcam opened: 1280×720
[VCAM] Device: Unity Video Capture
[RUN]  Kører – tryk Ctrl+C for at stoppe
```

Vælg nu **"Unity Video Capture"** som kamera i Teams.

### Opdater overlay-tekst

```powershell
# Sæt tekst i bunden (default)
curl -X POST http://localhost:5123/overlay -H "Content-Type: application/json" -d "{\"text\": \"Sprint Review – Q3\", \"position\": \"bottom\"}"

# Sæt tekst i toppen
curl -X POST http://localhost:5123/overlay -H "Content-Type: application/json" -d "{\"text\": \"Alexander – Team Volt\", \"position\": \"top\"}"

# Fjern overlay (tom tekst)
curl -X POST http://localhost:5123/overlay -H "Content-Type: application/json" -d "{\"text\": \"\"}"

# Se nuværende state
curl http://localhost:5123/overlay
```

Fra PowerShell (uden curl):
```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:5123/overlay `
  -ContentType "application/json" `
  -Body '{"text": "Demo mode", "position": "bottom"}'
```

### Valgfrie argumenter

| Argument    | Default | Beskrivelse                  |
|-------------|---------|------------------------------|
| `--port`    | 5123    | API-port                     |
| `--cam`     | 0       | Webcam-enhedsindex           |
| `--width`   | 1280    | Ønsket opløsningsbredde      |
| `--height`  | 720     | Ønsket opløsningshøjde       |
| `--fps`     | 30      | Target framerate             |

## Fejlfinding

**"Webcam index 0 could not be opened"**
→ Prøv `--cam 1` (eller højere). Andre apps kan låse kameraet.

**"Virtual camera failed"**
→ Unity Capture er ikke installeret, eller DLL'en blev ikke registreret. Kør `regsvr32` igen som admin.

**Teams viser ikke "Unity Video Capture"**
→ Genstart Teams efter installation af driveren.

**Overlay er langsomt / hakker**
→ Sænk opløsning (`--width 640 --height 480`) eller FPS (`--fps 15`).
