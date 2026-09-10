"""Verificacion independiente de una fase de relocalizacion.

Uso:
  python verify_relocation.py snapshot server.py  nombre1 nombre2 ...
  python verify_relocation.py check    destino.py nombre1 nombre2 ...

Toma el texto exacto (byte a byte) de cada unidad tal como esta en el archivo
origen, y despues lo busca en el destino y compara. Resuelve todo por AST desde
cero: no usa los numeros de linea del script de extraccion.
"""
import ast
import io
import json
import sys
import tokenize

SNAP = "/tmp/relocation_snapshot.json"


def collect(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    lines = src.splitlines(keepends=True)
    out = {}
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
            out.setdefault(node.name, []).append("".join(lines[start - 1:node.end_lineno]))
    return out


def dedent_block(text, n):
    """Dedent respetando las filas interiores de un string multilinea: esas
    filas nunca recibieron padding, asi que tampoco se les puede quitar."""
    protected = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.STRING and tok.end[0] != tok.start[0]:
                for r in range(tok.start[0] + 1, tok.end[0] + 1):
                    protected.add(r)
    except tokenize.TokenError:
        pass
    out = []
    for i, line in enumerate(text.splitlines(keepends=True), start=1):
        if i in protected or not line.strip():
            out.append(line)
        else:
            out.append(line[n:] if line.startswith(" " * n) else line)
    return "".join(out)


def normalise(text):
    """Solo revierte el swap de decorador; nada mas."""
    return text.replace("@router.", "@api_router.", 1).rstrip("\n")


def main():
    cmd, path, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    units = collect(path)

    if cmd == "snapshot":
        snap, missing = {}, []
        for name in names:
            found = units.get(name)
            if not found:
                missing.append(name)
                continue
            if len(found) > 1:
                print(f"AVISO: {name} aparece {len(found)} veces en {path}")
            snap[name] = found[0]
        if missing:
            print("FALTAN en", path, ":", missing)
            sys.exit(1)
        json.dump(snap, open(SNAP, "w"))
        print(f"Snapshot de {len(snap)} unidades ({sum(u.count(chr(10)) for u in snap.values())} lineas) -> {SNAP}")
        return

    snap = json.load(open(SNAP))
    ok, bad = 0, []
    for name, original in snap.items():
        found = units.get(name)
        if not found:
            bad.append((name, "NO EXISTE en el destino"))
            continue
        cand = found[0]
        if any(normalise(v) == normalise(original) for v in (cand, dedent_block(cand, 4))):
            ok += 1
        else:
            bad.append((name, "TEXTO DISTINTO"))
    print(f"Identicas byte a byte: {ok}/{len(snap)}")
    for name, why in bad:
        print(f"  FALLO {name}: {why}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
