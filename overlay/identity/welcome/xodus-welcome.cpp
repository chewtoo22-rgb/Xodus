// SPDX-License-Identifier: GPL-3.0-or-later
#include <QApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFileInfo>
#include <QFont>
#include <QFrame>
#include <QHBoxLayout>
#include <QIcon>
#include <QImage>
#include <QLabel>
#include <QLinearGradient>
#include <QMessageBox>
#include <QPaintEvent>
#include <QPainter>
#include <QPixmap>
#include <QProcess>
#include <QPushButton>
#include <QUrl>
#include <QVBoxLayout>
#include <QWidget>

namespace {
constexpr auto kWallpaper = "/usr/share/wallpapers/Xodus/xodus-wallpaper.png";
constexpr auto kIcon = "/usr/share/pixmaps/xodus-app-icon.png";
constexpr auto kInstaller = "/usr/local/bin/bin_install";

class Canvas : public QWidget {
public:
    explicit Canvas(const QPixmap &wallpaper, QWidget *parent = nullptr)
        : QWidget(parent), wallpaper_(wallpaper) {}

protected:
    void paintEvent(QPaintEvent *) override {
        QPainter painter(this);
        painter.setRenderHint(QPainter::SmoothPixmapTransform);
        painter.fillRect(rect(), QColor("#09090D"));
        const QSize scaled = wallpaper_.size().scaled(size(), Qt::KeepAspectRatioByExpanding);
        const QRect source(QPoint((scaled.width() - width()) / 2,
                                  (scaled.height() - height()) / 2), size());
        painter.drawPixmap(rect(), wallpaper_.scaled(scaled, Qt::KeepAspectRatio,
                                                     Qt::SmoothTransformation), source);
        QLinearGradient shade(0, 0, width(), 0);
        shade.setColorAt(0.0, QColor(9, 9, 15, 250));
        shade.setColorAt(0.60, QColor(15, 12, 25, 230));
        shade.setColorAt(1.0, QColor(19, 12, 31, 120));
        painter.fillRect(rect(), shade);
    }

private:
    QPixmap wallpaper_;
};

QLabel *label(const QString &text, int size, bool bold = false) {
    auto *item = new QLabel(text);
    QFont font("Noto Sans", size);
    font.setBold(bold);
    item->setFont(font);
    item->setWordWrap(true);
    item->setStyleSheet("color: #F6F4FA; background: transparent;");
    return item;
}

void showLaunchError(QWidget *parent, const QString &action) {
    QMessageBox::warning(parent, QObject::tr("Could not open %1").arg(action),
                         QObject::tr("The required application is unavailable in this session."));
}

class Welcome final : public Canvas {
public:
    Welcome(const QPixmap &wallpaper, const QPixmap &icon)
        : Canvas(wallpaper) {
        const bool liveSession = QFileInfo(QStringLiteral("/run/archiso/bootmnt")).isDir();
        setWindowTitle(tr("Welcome to Xodus"));
        setWindowIcon(QIcon(icon));
        setMinimumSize(760, 490);
        resize(900, 560);

        auto *layout = new QVBoxLayout(this);
        layout->setContentsMargins(46, 38, 46, 34);
        layout->setSpacing(0);

        auto *brand = new QHBoxLayout;
        auto *mark = new QLabel;
        mark->setPixmap(icon.scaled(46, 46, Qt::KeepAspectRatio, Qt::SmoothTransformation));
        mark->setFixedSize(46, 46);
        brand->addWidget(mark);
        brand->addSpacing(12);
        auto *name = label(QStringLiteral("XODUS"), 15, true);
        name->setStyleSheet("color: #F6F4FA; letter-spacing: 3px;");
        brand->addWidget(name);
        brand->addStretch();
        layout->addLayout(brand);
        layout->addStretch(2);

        auto *eyebrow = label(liveSession ? tr("LIVE DESKTOP  /  FIRST LOOK")
                                          : tr("YOUR DESKTOP  /  FIRST LOOK"), 10, true);
        eyebrow->setStyleSheet("color: #BBA9E8; letter-spacing: 2px;");
        layout->addWidget(eyebrow);
        layout->addSpacing(13);
        auto *title = label(tr("Welcome to Xodus."), 31, true);
        layout->addWidget(title);
        layout->addSpacing(10);
        auto *description = label(tr("A calm place to explore, make things, and make it yours."), 14);
        description->setMaximumWidth(550);
        description->setStyleSheet("color: #D6D0E1;");
        layout->addWidget(description);
        layout->addSpacing(29);

        auto *card = new QFrame;
        card->setObjectName("introCard");
        card->setMaximumWidth(575);
        card->setStyleSheet("#introCard { background: rgba(25, 21, 36, 224);"
                            " border: 1px solid #645575; border-radius: 14px; }");
        auto *cardLayout = new QVBoxLayout(card);
        cardLayout->setContentsMargins(19, 15, 19, 15);
        cardLayout->setSpacing(5);
        auto *cardTitle = label(tr("Take a look around"), 13, true);
        auto *cardBody = label(liveSession
                                   ? tr("Open your files or settings. Install only when you are ready.")
                                   : tr("Open your files or settings and make this space yours."), 11);
        cardBody->setStyleSheet("color: #C8C1D4;");
        cardLayout->addWidget(cardTitle);
        cardLayout->addWidget(cardBody);
        layout->addWidget(card);
        layout->addSpacing(20);

        auto *actions = new QHBoxLayout;
        actions->setSpacing(10);
        auto *files = new QPushButton(tr("Explore files"));
        auto *settings = new QPushButton(tr("Settings"));
        if (liveSession) {
            auto *install = new QPushButton(tr("Install Xodus"));
            install->setObjectName("primary");
            install->setToolTip(tr("Opens the Xodus installer. No disk is changed by this button."));
            install->setCursor(Qt::PointingHandCursor);
            install->setMinimumHeight(42);
            actions->addWidget(install);
            connect(install, &QPushButton::clicked, this, [this] {
                if (!QFileInfo(QString::fromLatin1(kInstaller)).isFile() ||
                    !QProcess::startDetached(QStringLiteral("/usr/bin/bash"),
                                             {QString::fromLatin1(kInstaller)})) {
                    showLaunchError(this, tr("the installer"));
                }
            });
        }
        for (auto *button : {files, settings}) {
            button->setCursor(Qt::PointingHandCursor);
            button->setMinimumHeight(42);
            actions->addWidget(button);
        }
        actions->addStretch();
        layout->addLayout(actions);
        layout->addStretch(1);

        auto *footer = label(tr("XODUS    •    MAKE IT YOURS"), 9, true);
        footer->setStyleSheet("color: #ACA3BC; letter-spacing: 1px;");
        layout->addWidget(footer);

        setStyleSheet("QPushButton { color: #F5F2F9; background: #292334;"
                      " border: 1px solid #6F607F; border-radius: 8px; padding: 0 17px; }"
                      "QPushButton:hover { background: #433750; }"
                      "QPushButton:focus { border: 2px solid #D4C2F4; }"
                      "QPushButton#primary { color: #140E1D; background: #C9B3EC;"
                      " border-color: #C9B3EC; font-weight: bold; }"
                      "QPushButton#primary:hover { background: #E0D1F5; }");

        connect(files, &QPushButton::clicked, this, [this] {
            if (!QDesktopServices::openUrl(QUrl::fromLocalFile(QDir::homePath()))) {
                showLaunchError(this, tr("Files"));
            }
        });
        connect(settings, &QPushButton::clicked, this, [this] {
            if (!QFileInfo(QStringLiteral("/usr/bin/systemsettings1")).isExecutable() ||
                !QProcess::startDetached(QStringLiteral("/usr/bin/systemsettings1"), QStringList{})) {
                showLaunchError(this, tr("Settings"));
            }
        });
    }
};
} // namespace

int main(int argc, char **argv) {
    QApplication::setAttribute(Qt::AA_EnableHighDpiScaling);
    QApplication app(argc, argv);
    const QPixmap wallpaper(QString::fromLatin1(kWallpaper));
    const QPixmap icon(QString::fromLatin1(kIcon));
    if (wallpaper.isNull() || icon.isNull()) {
        qCritical("Xodus Welcome artwork is missing or unreadable");
        return 70;
    }
    Welcome window(wallpaper, icon);
    window.show();
    if (app.arguments().contains(QStringLiteral("--self-test"))) {
        app.processEvents();
        QPixmap render(window.size());
        render.fill(Qt::transparent);
        window.render(&render);
        const QImage frame = render.toImage();
        const QString output = qEnvironmentVariable("XODUS_WELCOME_RENDER_PATH");
        if (!output.isEmpty() && !frame.save(output, "PNG")) {
            qCritical("Could not save the Xodus Welcome review frame");
            return 70;
        }
        return frame.isNull() || frame.pixelColor(frame.width() / 2,
                                                  frame.height() / 2).alpha() == 0
                   ? 70 : 0;
    }
    return app.exec();
}
