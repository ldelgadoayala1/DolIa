import os
import subprocess

# Archivos a visualizar
files = [
    "worker/main.py",
    "worker/sse_queue.py",
    "api/main.py",
]

output_file = "test/project_snapshot.txt"

os.makedirs("test", exist_ok=True)

with open(output_file, "w", encoding="utf-8") as out:

    # ─── Estructura del proyecto ───────────────────────────────────────
    out.write("=" * 60 + "\n")
    out.write("🗂️  PROJECT STRUCTURE\n")
    out.write("=" * 60 + "\n")
    try:
        result = subprocess.run(
            [
                "find", ".",
                "-type", "f",
                "-not", "-path", "./.git/*",
                "-not", "-path", "./node_modules/*",
                "-not", "-path", "./__pycache__/*",
                "-not", "-path", "./.venv/*",
                "-not", "-path", "./venv/*",
                "-not", "-path", "./*.egg-info/*",
            ],
            capture_output=True, text=True
        )
        out.write(result.stdout + "\n")
    except Exception as e:
        out.write(f"⚠️  No se pudo obtener estructura: {e}\n\n")

    # ─── Contenido de archivos específicos ────────────────────────────
    for filepath in files:
        out.write("=" * 60 + "\n")
        out.write(f"📄 FILE: {filepath}\n")
        out.write("=" * 60 + "\n")

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            out.write(content + "\n")
        else:
            out.write(f"⚠️  Archivo no encontrado: {filepath}\n")

        out.write("\n")

    # ─── Búsqueda automática de tasks.py ──────────────────────────────
    out.write("=" * 60 + "\n")
    out.write("🔍 BÚSQUEDA: tasks.py\n")
    out.write("=" * 60 + "\n")
    try:
        result = subprocess.run(
            [
                "find", ".",
                "-name", "tasks.py",
                "-not", "-path", "./.git/*",
            ],
            capture_output=True, text=True
        )
        found_tasks = result.stdout.strip().splitlines()
        if found_tasks:
            for task_path in found_tasks:
                out.write(f"\n📄 FILE: {task_path}\n")
                out.write("-" * 40 + "\n")
                try:
                    with open(task_path, "r", encoding="utf-8") as f:
                        out.write(f.read() + "\n")
                except Exception as e:
                    out.write(f"⚠️  Error leyendo {task_path}: {e}\n")
        else:
            out.write("⚠️  No se encontró ningún tasks.py\n")
    except Exception as e:
        out.write(f"⚠️  Error buscando tasks.py: {e}\n")

print(f"✅ Snapshot guardado en: {output_file}")