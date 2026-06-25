"""django-coupling: coupling analysis for Django/Python projects.

Measures coupling along three dimensions (Khononov / cargo-coupling):
  - Strength   : how tightly a module depends on another (contract<model<functional<intrusive)
  - Distance   : structural separation, with Django layer semantics (views>serializers>services>models)
  - Volatility : how often the target changes (from git history)

and combines them into a Balance Score. High coupling is only a problem when it is
*unbalanced* (e.g. strong + far, or strong + volatile).
"""

__version__ = "0.1.0"
