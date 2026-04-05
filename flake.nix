{
  description = "Awesome Visualizer - data-driven explorer for awesome lists";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonEnv = python.withPackages (ps: with ps; [
          requests
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.gh
            pkgs.git
            pkgs.jq
          ];

          shellHook = ''
            echo "awesome-visualizer dev shell"
            echo "  python: $(python --version)"
            echo "  gh:     $(gh --version | head -1)"
            echo ""
            echo "Commands:"
            echo "  python scripts/fetch_data.py   - Fetch repo data (needs GITHUB_TOKEN)"
            echo "  python -m http.server -d site  - Local dev server on :8000"
          '';
        };
      }
    );
}
