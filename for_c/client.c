#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libwebsockets.h>
#include <zlib.h>
#include <unistd.h>

#define URL "ws://localhost:8765"

// Функция для вычисления контрольной суммы
unsigned int calculate_checksum(const unsigned char *data, size_t len) {
    unsigned int checksum = crc32(0L, Z_NULL, 0);
    checksum = crc32(checksum, data, len);
    return checksum;
}

// Обратный вызов для обработки событий WebSocket
static int callback_websocket(struct lws *wsi, enum lws_callback_reasons reason, void *user, void *in, size_t len) {
    switch (reason) {
        case LWS_CALLBACK_CLIENT_ESTABLISHED:
            printf("Подключение установлено\n");
            break;

        case LWS_CALLBACK_CLIENT_RECEIVE:
            printf("Получены данные: длина %zu\n", len);

            if (len == 68) { // Проверяем длину полученных данных
                unsigned char received_data[64];
                unsigned int received_checksum;

                memcpy(received_data, in, 64);
                memcpy(&received_checksum, (unsigned char *)in + 64, 4);

                received_checksum = ntohl(received_checksum);

                unsigned int expected_checksum = calculate_checksum(received_data, 64);
                if (expected_checksum == received_checksum) {
                    printf("Контрольная сумма совпадает. Данные корректны.\n");
                } else {
                    printf("Ошибка: контрольная сумма не совпадает.\n");
                }
            } else {
                printf("Сломанные данные с сервера\n");
            }
            break;

        case LWS_CALLBACK_CLIENT_WRITEABLE:
            // Генерация и отправка данных
            {
                unsigned char binary_data[64];
                for (int i = 0; i < 64; ++i) {
                    binary_data[i] = rand() % 100 + 1;
                }

                unsigned int checksum = calculate_checksum(binary_data, 64);
                unsigned char data_with_checksum[68];
                memcpy(data_with_checksum, binary_data, 64);
                *(unsigned int *)(data_with_checksum + 64) = htonl(checksum);

                lws_write(wsi, data_with_checksum, sizeof(data_with_checksum), LWS_WRITE_BINARY);
                printf("Данные отправлены\n");
            }
            break;

        case LWS_CALLBACK_CLOSED:
            printf("Подключение закрыто\n");
            break;

        default:
            break;
    }

    return 0;
}

int main() {
    struct lws_context_creation_info info;
    memset(&info, 0, sizeof(info));

    // Настройка контекста
    info.port = CONTEXT_PORT_NO_LISTEN; // Клиент не слушает порт
    info.protocols = (struct lws_protocols[]){
        {"http", callback_websocket, 0, 0},
        {NULL, NULL, 0, 0} // Завершение списка протоколов
    };
    info.gid = -1;
    info.uid = -1;

    struct lws_context *context = lws_create_context(&info);
    if (!context) {
        fprintf(stderr, "Ошибка создания контекста\n");
        return -1;
    }

    struct lws_client_connect_info connect_info;
    memset(&connect_info, 0, sizeof(connect_info));
    connect_info.context = context;
    connect_info.address = "localhost";
    connect_info.port = 8765;
    connect_info.path = "/";
    connect_info.host = connect_info.address;
    connect_info.origin = connect_info.address;
    connect_info.protocol = "http";

    struct lws *wsi = lws_client_connect_via_info(&connect_info);
    if (!wsi) {
        fprintf(stderr, "Ошибка подключения к серверу\n");
        lws_context_destroy(context);
        return -1;
    }

    printf("Клиент запущен. Ожидание событий...\n");

    int send_data = 0;
    while (1) {
        lws_service(context, 50); // Обработка событий

        if (send_data) {
            // Генерация и отправка данных
            unsigned char binary_data[64];
            for (int i = 0; i < 64; ++i) {
                binary_data[i] = rand() % 100 + 1;
            }

            unsigned int checksum = calculate_checksum(binary_data, 64);
            unsigned char data_with_checksum[68];
            memcpy(data_with_checksum, binary_data, 64);
            *(unsigned int *)(data_with_checksum + 64) = htonl(checksum);

            lws_write(wsi, data_with_checksum, sizeof(data_with_checksum), LWS_WRITE_BINARY);
            printf("Данные отправлены\n");

            send_data = 0;
        }

        usleep(100000); // Задержка перед отправкой следующих данных

        // Отправка данных каждые 100 мс
        send_data = 1;
    }

    lws_context_destroy(context);
    return 0;
}
