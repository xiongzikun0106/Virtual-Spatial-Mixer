import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Virtual Spatial Mixer")
    parser.add_argument(
        "--webview",
        action="store_true",
        help="使用 pywebview（Windows 为 WebView2）+ TypeScript 前端",
    )
    args = parser.parse_args()

    if args.webview:
        from src.webview_host import run_webview_app

        run_webview_app()
        return

    from PyQt6.QtWidgets import QApplication
    from src.app import MainWindow

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
