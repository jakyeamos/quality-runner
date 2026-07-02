class QualityRunner < Formula
  include Language::Python::Virtualenv

  desc "Standalone audit-and-plan quality orchestrator with CLI and MCP surfaces"
  homepage "https://github.com/jakyeamos/quality-runner"
  url "https://files.pythonhosted.org/packages/source/q/quality-runner/quality_runner-0.2.0.tar.gz"
  sha256 "REPLACE_AFTER_PYPI_RELEASE"
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
