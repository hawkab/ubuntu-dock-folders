// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 Grigory Olshansky

#include <QCoreApplication>
#include <QFile>
#include <QJSEngine>
#include <QTextStream>
#include <QJsonDocument>
#include <QJsonObject>

namespace {
constexpr qint64 requestLimit = 4 * 1024 * 1024;

int serve(QJSEngine &engine, const QJSValue &module, QFile &input)
{
    QTextStream output(stdout);
    while (true) {
        const QByteArray line = input.readLine(requestLimit + 2);
        if (line.isEmpty()) break;
        if (line.size() > requestLimit || !line.endsWith('\n')) return 2;
        QJSValue result;
        QJSValue parser = engine.globalObject().property("JSON").property("parse");
        const QJSValue request = parser.call({QString::fromUtf8(line)});
        if (request.isError()) result = request;
        else {
            const QJSValue method = module.property(request.property("method").toString());
            result = method.isCallable() ? method.call({request.property("value")})
                : engine.newErrorObject(QJSValue::TypeError,QStringLiteral("Unknown core method"));
        }
        if (result.isError()) {
            output << QJsonDocument(QJsonObject{{"ok",false},{"error",result.toString()}}).toJson(QJsonDocument::Compact) << '\n';
        } else {
            QJSValue stringify = engine.globalObject().property("JSON").property("stringify");
            output << "{\"ok\":true,\"result\":" << stringify.call({result}).toString() << "}\n";
        }
        output.flush();
    }
    return 0;
}
}

/** Execute the portable folder API from one JSON request on stdin. */
int main(int argc, char **argv)
{
    QCoreApplication application(argc, argv);
    if (argc != 2 && argc != 3) return 2;
    QFile input;
    if (!input.open(stdin, QIODevice::ReadOnly)) return 2;
    QJSEngine engine;
    const QJSValue module = engine.importModule(QString::fromLocal8Bit(argv[1]));
    if (module.isError()) {
        QTextStream(stderr) << module.toString() << '\n';
        return 1;
    }
    if (argc == 3 && QString::fromLocal8Bit(argv[2]) == QStringLiteral("--server"))
        return serve(engine,module,input);
    QByteArray payload;
    while (payload.size() <= 4 * 1024 * 1024) {
        const QByteArray chunk = input.read(65536);
        if (chunk.isEmpty()) break;
        payload.append(chunk);
    }
    if (payload.size() > 4 * 1024 * 1024) return 2;
    QJSValue parser = engine.globalObject().property("JSON").property("parse");
    const QJSValue request = parser.call({QString::fromUtf8(payload)});
    QJSValue transact = module.property(argc == 3 ? QString::fromLocal8Bit(argv[2]) : QStringLiteral("transact"));
    const QJSValue result = transact.call({request});
    if (module.isError() || request.isError() || result.isError()) {
        const QJSValue error = module.isError() ? module : request.isError() ? request : result;
        QTextStream(stderr) << error.property("fileName").toString() << ":" << error.property("lineNumber").toInt() << " " << error.toString() << '\n';
        return 1;
    }
    QJSValue stringify = engine.globalObject().property("JSON").property("stringify");
    QTextStream(stdout) << stringify.call({result}).toString() << '\n';
    return 0;
}
