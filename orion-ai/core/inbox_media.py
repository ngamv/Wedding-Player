"""Extraction locale des pièces mémoire."""
import os
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

AUDIO_FORMATS = {".wav": "wav", ".mp3": "mp3", ".m4a": "mov", ".ogg": "ogg", ".flac": "flac"}

MEDIA = {
    ".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".ogg": "audio/ogg", ".flac": "audio/flac",
}


def extract_media(filename, payload):
    suffix = Path(filename).suffix.lower()
    mime = MEDIA.get(suffix)
    if not mime or not payload:
        raise ValueError("Sélectionnez un PDF, un JPEG ou un fichier audio pris en charge.")
    if suffix == ".pdf" and not payload.startswith(b"%PDF-"):
        raise ValueError("Le contenu du fichier ne correspond pas à un PDF.")
    if mime == "image/jpeg" and not payload.startswith(b"\xff\xd8\xff"):
        raise ValueError("Le contenu du fichier ne correspond pas à un JPEG.")
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename.replace("\\", "/").rsplit("/", 1)[-1])[:180]
    warning = None
    with TemporaryDirectory() as temp:
        work = Path(temp)
        source = work / ("input" + suffix)
        output = work / "extracted.txt"
        source.write_bytes(payload)
        try:
            def run(args, timeout):
                subprocess.run(args, check=True, timeout=timeout,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            language = os.environ.get("ORION_OCR_LANG", "fra+eng")
            if suffix == ".pdf":
                run(["pdftotext", "-layout", "-enc", "UTF-8", "-l", "100", str(source), str(output)], 35)
                with output.open("rb") as text_file:
                    has_text = bool(text_file.read(200000).strip())
                if not has_text:
                    run(["pdftoppm", "-f", "1", "-l", "5", "-scale-to", "2000", "-jpeg",
                         str(source), str(work / "page")], 35)
                    parts = []
                    for page in sorted(work.glob("page-*.jpg")):
                        run(["tesseract", str(page), str(page.with_suffix("")), "-l", language], 25)
                        with page.with_suffix(".txt").open(encoding="utf-8", errors="replace") as page_text:
                            parts.append(page_text.read(50001))
                    output.write_text("\n\n".join(parts), encoding="utf-8")
                    warning = "OCR du PDF scanné limité aux cinq premières pages."
            elif mime == "image/jpeg":
                run(["tesseract", str(source), str(output.with_suffix("")), "-l",
                     language], 60)
            else:
                model = os.environ.get("ORION_WHISPER_MODEL")
                if not model or not Path(model).is_file():
                    raise FileNotFoundError("Modèle Whisper absent.")
                wav = work / "audio.wav"
                run(["ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file",
                     "-f", AUDIO_FORMATS[suffix], "-i", str(source), "-t", "600", "-ar", "16000", "-ac", "1", str(wav)], 60)
                run(["whisper-cli", "-m", model, "-l", "auto", "-f", str(wav),
                     "-otxt", "-of", str(output.with_suffix(""))], 300)
            with output.open(encoding="utf-8", errors="replace") as text:
                content = text.read(50001).strip()
            if len(content) > 50000:
                warning = "Texte extrait limité à 50 000 caractères."
            elif not content:
                warning = "Aucun texte extrait. Ajoutez une transcription ou un texte manuellement."
        except FileNotFoundError:
            content = ""
            warning = "Extraction indisponible. Vérifiez les outils locaux et leur configuration."
        except (OSError, subprocess.SubprocessError):
            content = ""
            warning = "L’extraction locale a échoué. Vous pouvez compléter le texte manuellement."
    return filename, mime, content[:50000], warning
