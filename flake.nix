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
    in
    eachSystem
      supportedSystems
      (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          devShell = with pkgs;
            mkShell {
              nativeBuildInputs = [ python37 poetry ];
            };
          defaultPackage = with pkgs.python3Packages; buildPythonPackage {
            pname = "clion";
            version = "0.3.2";
            format = "pyproject";

            disabled = pythonOlder "3.7";

            buildInputs = [ poetry ];

            src = self;
          };
        });
}
