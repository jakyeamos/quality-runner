class QualityRunner < Formula
  include Language::Python::Virtualenv

  desc "Standalone audit-and-plan quality orchestrator with CLI and MCP surfaces"
  homepage "https://github.com/jakyeamos/quality-runner"
  url "https://files.pythonhosted.org/packages/87/ab/862fb6462a7f253a715de26fd7c7c8bf799779cc61383551104427959850/quality_runner-0.2.0.tar.gz"
  sha256 "cdc013f7913d44d6bcc41b749b8d517790e7bc31885b9005a4c2fb2e112479ba"
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/quality-runner --version")
    assert_match "ready", shell_output("#{bin}/quality-runner doctor --json")
  end
end
