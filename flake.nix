{
  description = "Static coupling-analysis CLI for Django/Python projects (Strength x Distance x Volatility)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        py = pkgs.python3Packages;

        django-coupling = py.buildPythonApplication {
          pname = "django-coupling";
          version = "0.1.0";
          pyproject = true;
          src = ./.;

          build-system = [ py.setuptools ];

          # No runtime Python deps. The tool shells out to `git` for the
          # volatility signal, so put git on the wrapped program's PATH.
          makeWrapperArgs = [ "--prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.git ]}" ];

          nativeCheckInputs = [ py.pytestCheckHook pkgs.git ];

          meta = with pkgs.lib; {
            description = "Static coupling-analysis CLI for Django/Python projects";
            homepage = "https://github.com/Yuto729/django-coupling";
            license = licenses.mit;
            mainProgram = "django-coupling";
          };
        };
      in
      {
        packages.default = django-coupling;
        packages.django-coupling = django-coupling;

        # `nix run github:Yuto729/django-coupling -- <path>`
        apps.default = flake-utils.lib.mkApp { drv = django-coupling; };

        devShells.default = pkgs.mkShell {
          packages = [ (pkgs.python3.withPackages (ps: [ ps.pytest ])) pkgs.git ];
        };
      });
}
