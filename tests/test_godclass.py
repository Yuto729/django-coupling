import ast

from django_coupling.godclass import lcom4, _instance_methods, find_god_classes


def _methods(src):
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
    return _instance_methods(cls)


def test_cohesive_class_is_one_component():
    # all methods share self.total -> single component, even if many methods
    src = (
        "class Account:\n"
        "    def __init__(self): self.total = 0\n"
        "    def add(self, x): self.total += x\n"
        "    def sub(self, x): self.total -= x\n"
        "    def show(self): return self.total\n"
    )
    assert lcom4(_methods(src)) == 1


def test_god_class_splits_into_components():
    # two unrelated clusters: {a,b} touch self.x ; {c,d} touch self.y
    src = (
        "class God:\n"
        "    def a(self): self.x = 1\n"
        "    def b(self): return self.x\n"
        "    def c(self): self.y = 2\n"
        "    def d(self): return self.y\n"
    )
    assert lcom4(_methods(src)) == 2


def test_method_call_links_components():
    # b calls self.a() -> linked even without shared field
    src = (
        "class C:\n"
        "    def a(self): return 1\n"
        "    def b(self): return self.a()\n"
        "    def c(self): self.z = 1\n"
        "    def d(self): return self.z\n"
    )
    # {a,b} one component, {c,d} another
    assert lcom4(_methods(src)) == 2


def test_find_god_classes_e2e(tmp_path):
    root = tmp_path / "proj" / "api" / "services"
    root.mkdir(parents=True)
    (tmp_path / "proj" / "api" / "__init__.py").write_text("")
    (root / "__init__.py").write_text("")
    (root / "ok.py").write_text(
        "class Good:\n"
        "    def __init__(self): self.n = 0\n"
        "    def inc(self): self.n += 1\n"
        "    def get(self): return self.n\n"
        "    def reset(self): self.n = 0\n"
    )
    (root / "bad.py").write_text(
        "import os\nimport sys\n"
        "class Big:\n"
        "    def a(self): self.x = os.getpid()\n"
        "    def b(self): return self.x\n"
        "    def c(self): self.y = 1\n"
        "    def d(self): return self.y\n"
        "    def e(self): self.z = sys.argv\n"
        "    def f(self): return self.z\n"
    )
    god = find_god_classes(str(tmp_path / "proj" / "api"))
    names = {g["class"] for g in god}
    assert "api.services.bad.Big" in names
    assert "api.services.ok.Good" not in names  # cohesive -> not flagged
    big = next(g for g in god if g["class"] == "api.services.bad.Big")
    assert big["lcom4"] == 3 and big["methods"] == 6
