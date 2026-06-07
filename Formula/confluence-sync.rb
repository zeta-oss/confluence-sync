class ConfluenceSync < Formula
  include Language::Python::Virtualenv

  desc "Sync Markdown documentation to Confluence"
  homepage "https://github.com/zeta-oss/confluence-sync"
  url "https://github.com/zeta-oss/confluence-sync/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "PLACEHOLDER"  # Updated by scripts/publish-brew.sh at release time
  license "MIT"

  depends_on "python@3.12"
  depends_on "git"

  resource "requests" do
    url "https://files.pythonhosted.org/packages/source/r/requests/requests-2.32.3.tar.gz"
    sha256 "55365417734eb18255590a9f9b84e76f42e71c6a90ddd1e97d7e60e3a3ebcd75"
  end

  resource "markdown" do
    url "https://files.pythonhosted.org/packages/source/M/Markdown/Markdown-3.6.tar.gz"
    sha256 "ed4f41f6daecbe9173e3732324b212c3b8b64e5a7774a2cc45e94d558efb4d00"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/source/P/PyYAML/PyYAML-6.0.1.tar.gz"
    sha256 "bfdf460b1736c775f2ba9f6a92bca30bc2095067b8a9d77876d1fad6cc3b4a43"
  end

  resource "tabulate" do
    url "https://files.pythonhosted.org/packages/source/t/tabulate/tabulate-0.9.0.tar.gz"
    sha256 "0095b12bf5966d58a9a2bc06f8ce3e3968d9c4e4a99282fa1a9e3f9f50e9de5e"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/source/c/click/click-8.1.7.tar.gz"
    sha256 "ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
  end

  resource "python-dotenv" do
    url "https://files.pythonhosted.org/packages/source/p/python-dotenv/python-dotenv-1.0.1.tar.gz"
    sha256 "e324ee90a023d808f1959c46bcbc04446a10ced277783dc6ee09987c37ec10ca"
  end

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      Optional: install Node.js mermaid-cli for reliable diagram rendering:
        npm install -g @mermaid-js/mermaid-cli

      Store your Confluence API token:
        mkdir -p ~/.local/confluence-sync
        echo 'CONFLUENCE_TOKEN=your-token-here' >> ~/.local/confluence-sync/.env

      Initialize a content repo:
        cd ~/your-content-repo
        confluence-sync init
    EOS
  end

  test do
    system "#{bin}/confluence-sync", "--version"
    system "#{bin}/confluence-sync", "doctor", "--help"
    system "#{bin}/confluence-sync", "sync", "--help"
  end
end
