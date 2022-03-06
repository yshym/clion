{
  description = "Clinic";

  inputs = {
    nixpkgs.url = "github:yevhenshymotiuk/nixpkgs/release-21.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShell = with pkgs;
          mkShell {
            nativeBuildInputs = [ python37 poetry ];
          };
      });
}
