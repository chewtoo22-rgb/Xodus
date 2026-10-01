// SPDX-License-Identifier: GPL-2.0-or-later
// Render the repo's original vector frame for BorderImage's PNG interface.
#include <QGuiApplication>
#include <QSvgRenderer>
#include <QPainter>
#include <QImage>
int main(int argc, char **argv) {
    QGuiApplication app(argc, argv);
    if (argc != 3) return 64;
    QSvgRenderer svg(QString::fromLocal8Bit(argv[1]));
    if (!svg.isValid()) return 65;
    QImage frame(96, 96, QImage::Format_ARGB32_Premultiplied);
    frame.fill(Qt::transparent);
    QPainter painter(&frame);
    svg.render(&painter);
    painter.end();
    return frame.save(QString::fromLocal8Bit(argv[2]), "PNG") ? 0 : 74;
}
