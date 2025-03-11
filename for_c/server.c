#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sqlite3.h>
#include <libwebsockets.h>
#include <zlib.h>

#define DATABASE_URL "my_database.db"
#define TABLE_NAME "waveform_data"

unsigned int calculate_checksum(const unsigned char *data, size_t len) {
    unsigned int checksum = crc32(0L, Z_NULL, 0);
    checksum = crc32(checksum, data, len);
    return checksum;
}

static int callback_http(struct lws *wsi, enum lws_callback_reasons reason, void *user, void *in, size_t len) {
    switch (reason) {
        case LWS_CALLBACK_ESTABLISHED:
            printf("Пользователь подключился\n");
            break;

        case LWS_CALLBACK_RECEIVE:

            if (len == 68) { 
                unsigned char received_data[64];
                unsigned int received_checksum;

                memcpy(received_data, in, 64);
                memcpy(&received_checksum, (unsigned char *)in + 64, 4);

                received_checksum = ntohl(received_checksum);

                unsigned int expected_checksum = calculate_checksum(received_data, 64);
                if (expected_checksum == received_checksum) {
                    printf("Контрольная сумма совпадает. Данные корректны.\n");

                    sqlite3 *db;
                    sqlite3_stmt *stmt;
                    int rc = sqlite3_open(DATABASE_URL, &db);
                    if (rc) {
                        printf("Ошибка открытия базы данных: %s\n", sqlite3_errmsg(db));
                        return 0;
                    }

                    const char *sql = "INSERT INTO waveform_data (time_data, voltage_data) VALUES (?, ?)";
                    rc = sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
                    if (rc != SQLITE_OK) {
                        printf("Ошибка подготовки запроса: %s\n", sqlite3_errmsg(db));
                        sqlite3_close(db);
                        return 0;
                    }

                    char data_str[64 * 3 + 1];
                    for (int i = 0; i < 64; ++i) {
                        sprintf(data_str + i * 3, "%02x ", received_data[i]);
                    }

                    sqlite3_bind_text(stmt, 1, data_str, -1, SQLITE_STATIC);
                    sqlite3_bind_text(stmt, 2, data_str, -1, SQLITE_STATIC);

                    rc = sqlite3_step(stmt);
                    if (rc != SQLITE_DONE) {
                        printf("Ошибка выполнения запроса: %s\n", sqlite3_errmsg(db));
                    }

                    sqlite3_finalize(stmt);
                    sqlite3_close(db);

                    printf("Данные сохранены в базу данных\n");
                } else {
                    printf("Ошибка: контрольная сумма не совпадает.\n");
                }
            } else {
                printf("Сломанные данные с сервера\n");
            }
            break;

        case LWS_CALLBACK_CLOSED:
            printf("Произошел дисконнект\n");
            break;

        default:
            break;
    }

    return 0;
}

int main() {
    sqlite3 *db;
    int rc = sqlite3_open(DATABASE_URL, &db);
    if (rc) {
        printf("Ошибка открытия базы данных: %s\n", sqlite3_errmsg(db));
        return 1;
    }

    const char *sql = "CREATE TABLE IF NOT EXISTS waveform_data (id INTEGER PRIMARY KEY, time_data TEXT, voltage_data TEXT)";
    rc = sqlite3_exec(db, sql, NULL, NULL, NULL);
    if (rc != SQLITE_OK) {
        printf("Ошибка создания таблицы: %s\n", sqlite3_errmsg(db));
    }

    sqlite3_close(db);

    struct lws_protocols protocol = {
        "http",
        callback_http,
        0,
        0,
    };

    struct lws_context_creation_info info;
    memset(&info, 0, sizeof(info));
    info.port = 8765;
    info.protocols = &protocol;
    info.gid = -1;
    info.uid = -1;

    struct lws_context *context = lws_create_context(&info);
    if (!context) {
        printf("Ошибка создания контекста\n");
        return 1;
    }

    printf("Сервер запущен на порту 8765\n");

    while (1) {
        lws_service(context, 50);
    }

    lws_context_destroy(context);
    return 0;
}
