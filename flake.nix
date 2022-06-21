{
  description = "Clion";

  inputs = {
    nixpkgs.url = "github:yevhenshymotiuk/nixpkgs/release-21.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    let
      inherit (flake-utils.lib) eachSystem;

      supportedSystems = [ "aarch64-linux" "x86_64-darwin" "x86_64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs supportedSystems (system: f system);
    in
    {
      overlay = final: prev: {
        clion = with prev.python3Packages; buildPythonPackage {
          pname = "clion";
          version = "0.3.2";
          format = "pyproject";

          disabled = pythonOlder "3.7";

          buildInputs = [ poetry ];

          src = self;
        };
      };

      defaultPackage = forAllSystems (system: (import nixpkgs {
        inherit system;
        overlays = [ self.overlay ];
      }).clion);

      nixosModules.clion = { pkgs, ... }: {
        nixpkgs.overlays = [ self.overlay ];
      };
    };
}
