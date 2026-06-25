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
    names = {(g["module"], g["class_name"]) for g in god}
    assert ("api.services.bad", "Big") in names
    assert ("api.services.ok", "Good") not in names  # cohesive -> not flagged
    big = next(g for g in god
               if g["module"] == "api.services.bad" and g["class_name"] == "Big")
    assert big["cohesion_components"] == 3 and big["methods"] == 6
    assert big["module_god_count"] == 1


def test_module_god_count_flags_multiple_in_one_file(tmp_path):
    root = tmp_path / "proj" / "api"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    # one file with TWO god classes (each splits into 2+ field clusters)
    (root / "dense.py").write_text(
        "class A:\n"
        "    def a1(self): self.x = 1\n"
        "    def a2(self): return self.x\n"
        "    def a3(self): self.y = 2\n"
        "    def a4(self): return self.y\n"
        "class B:\n"
        "    def b1(self): self.p = 1\n"
        "    def b2(self): return self.p\n"
        "    def b3(self): self.q = 2\n"
        "    def b4(self): return self.q\n"
    )
    god = find_god_classes(str(root))
    dense = [g for g in god if g["module"] == "api.dense"]
    assert {g["class_name"] for g in dense} == {"A", "B"}
    assert all(g["module_god_count"] == 2 for g in dense)
