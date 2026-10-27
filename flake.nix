{
  description = "Development shell for DMI Home Assistant";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { self, nixpkgs }: {
    devShells = nixpkgs.lib.genAttrs [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" "x86_64-darwin" ] (system: {
      default = let pkgs = import nixpkgs { inherit system; }; in pkgs.mkShell {
        packages = [ pkgs.python313 pkgs.python314 pkgs.uv pkgs.actionlint ];
      };
    });
  };
}
