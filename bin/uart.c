#include <libwebsockets.h>
#include <pthread.h>
#include <signal.h>
#include <string.h>
#include <unistd.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <sys/select.h>
#include <time.h>
#include <stdarg.h>
#include <stdbool.h>
#include <curl/curl.h>
#include <sys/time.h>

#define UART_BAUDRATE B115200
#define PACKET_SIZE 64
#define HTTP_SERVER_URL "http://127.0.0.1:8080/uart-data"
#define MAX_PORTS 2

static const uint8_t START_SEQ_TEMPERATURE[] = {0x01, 0x02, 0x03, 0x04};
static const uint8_t START_SEQ_HIGH_TEMPERATURE[] = {0x03, 0x03, 0x03, 0x03};
static const uint8_t START_SEQ_TRACTION[] = {0x05, 0x02, 0x03, 0x04};

static int uart_fd = -1;
static volatile bool running = true;
static pthread_mutex_t uart_mutex = PTHREAD_MUTEX_INITIALIZER;

typedef struct {
    double tempNormal1;
    double tempNormal2;
    double temp600_1;
    double temp600_2;
    double thrust1;
} sensor_data_t;

uint16_t calc_crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int j = 0; j < 8; j++) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
            crc &= 0xFFFF;
        }
    }
    return crc;
}

static size_t write_callback(void *contents, size_t size, size_t nmemb, void *userp) {
    return size * nmemb;
}

void send_uart_data_via_http(const sensor_data_t *sensor_data) {
    CURL *curl;
    CURLcode res;
    
    curl = curl_easy_init();
    
    if(curl) {
        char json_data[512];
        snprintf(json_data, sizeof(json_data),
                "{\"type\":\"sensor_data\",\"data\":{"
                "\"tempNormal1\":%.2f,"
                "\"tempNormal2\":%.2f,"
                "\"temp600_1\":%.2f,"
                "\"temp600_2\":%.2f,"
                "\"thrust1\":%.3f}}",
                sensor_data->tempNormal1,
                sensor_data->tempNormal2,
                sensor_data->temp600_1,
                sensor_data->temp600_2,
                sensor_data->thrust1);
        
        printf("Sending JSON: %s\n", json_data);
        
        curl_easy_setopt(curl, CURLOPT_URL, HTTP_SERVER_URL);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_data);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 2000L);
        
        struct curl_slist *headers = NULL;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        
        res = curl_easy_perform(curl);
        
        if(res != CURLE_OK) {
            fprintf(stderr, "HTTP send error: %s\n", curl_easy_strerror(res));
        } else {
            long response_code;
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response_code);
            printf("UART data sent via HTTP (status: %ld)\n", response_code);
        }
        
        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    }
}

void decode_high_temperature_payload(const uint8_t *payload, uint8_t command, 
                                   double *temp1, double *temp2) {
    if (payload == NULL || temp1 == NULL || temp2 == NULL) return;
    
    float temp1_f, temp2_f;
    memcpy(&temp1_f, payload, sizeof(float));
    memcpy(&temp2_f, payload + 4, sizeof(float));
    
    *temp1 = (double)temp1_f;
    *temp2 = (double)temp2_f;
}

void decode_temperature_payload(const uint8_t *payload, uint8_t command,
                              double *temp1, double *temp2) {
    if (payload == NULL || temp1 == NULL || temp2 == NULL) return;
    
    int16_t temp1_raw = (int16_t)(payload[0] | (payload[1] << 8));
    int16_t temp2_raw = (int16_t)(payload[2] | (payload[3] << 8));
    
    *temp1 = temp1_raw / 100.0;
    *temp2 = temp2_raw / 100.0;
}

double decode_traction_payload(const uint8_t *payload, uint8_t command) {
    if (payload == NULL) return 0.0;
    
    uint16_t weight = payload[2] | (payload[3] << 8);
    return weight / 1000.0;
}

bool compare_start_seq(const uint8_t *seq1, const uint8_t *seq2, size_t len) {
    return memcmp(seq1, seq2, len) == 0;
}

int uart_init(const char *port) {
    int fd = open(port, O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0) {
        fprintf(stderr, "Error opening %s: %s\n", port, strerror(errno));
        return -1;
    }
    
    struct termios tty;
    if (tcgetattr(fd, &tty) != 0) {
        fprintf(stderr, "Error getting termios attributes: %s\n", strerror(errno));
        close(fd);
        return -1;
    }
    
    cfsetospeed(&tty, UART_BAUDRATE);
    cfsetispeed(&tty, UART_BAUDRATE);
    
    tty.c_cflag = (tty.c_cflag & ~CSIZE) | CS8;
    tty.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
    tty.c_oflag &= ~OPOST;
    tty.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
    tty.c_cflag &= ~(PARENB | PARODD);
    tty.c_cflag &= ~CSTOPB;
    tty.c_cflag &= ~CRTSCTS;
    
    tty.c_cc[VMIN] = 0;
    tty.c_cc[VTIME] = 1;
    
    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        fprintf(stderr, "Error setting termios attributes: %s\n", strerror(errno));
        close(fd);
        return -1;
    }
    
    return fd;
}

int find_start_sequence(const uint8_t *buffer, size_t len, const uint8_t **found_seq) {
    for (size_t i = 0; i <= len - 4; i++) {
        if (compare_start_seq(&buffer[i], START_SEQ_TEMPERATURE, 4)) {
            *found_seq = START_SEQ_TEMPERATURE;
            return i;
        }
        if (compare_start_seq(&buffer[i], START_SEQ_HIGH_TEMPERATURE, 4)) {
            *found_seq = START_SEQ_HIGH_TEMPERATURE;
            return i;
        }
        if (compare_start_seq(&buffer[i], START_SEQ_TRACTION, 4)) {
            *found_seq = START_SEQ_TRACTION;
            return i;
        }
    }
    return -1;
}

void process_complete_packet(const uint8_t *packet, const uint8_t *expected_start) {
    uint8_t command = packet[4];
    uint8_t resp_ok = packet[5];
    uint8_t payload_len = packet[6];

    
    uint16_t calc_crc = calc_crc16(&packet[4], 58);
    uint16_t recv_crc = (packet[62] << 8) | packet[63];
    
    
    if (calc_crc == recv_crc) {
        printf("Valid packet received - Command: 0x%02X\n", command);
        
        sensor_data_t sensor_data = {0};
        const uint8_t *payload = &packet[7];
        
        if (compare_start_seq(expected_start, START_SEQ_TEMPERATURE, 4)) {
            decode_temperature_payload(payload, command, 
                                     &sensor_data.tempNormal1, 
                                     &sensor_data.tempNormal2);
            printf("Decoded temperatures: temp1=%.2f, temp2=%.2f\n",
                   sensor_data.tempNormal1, sensor_data.tempNormal2);
        }
        else if (compare_start_seq(expected_start, START_SEQ_TRACTION, 4)) {
            sensor_data.thrust1 = decode_traction_payload(payload, command);
            printf("Decoded weight: weight=%.3f\n", sensor_data.thrust1);
        }
        else if (compare_start_seq(expected_start, START_SEQ_HIGH_TEMPERATURE, 4)) {
            decode_high_temperature_payload(payload, command,
                                          &sensor_data.temp600_1,
                                          &sensor_data.temp600_2);
            printf("Decoded high temperatures: high_temp1=%.2f, high_temp2=%.2f\n",
                   sensor_data.temp600_1, sensor_data.temp600_2);
        }
        
        send_uart_data_via_http(&sensor_data);
    } else {
        printf("Invalid CRC (got %04X, calc %04X)\n", recv_crc, calc_crc);
    }
}

void* uart_reader_thread(void* arg) {
    uint8_t buffer[512];
    size_t buffer_len = 0;
    bool waiting_for_packet = false;
    const uint8_t *expected_packet_start = NULL;
    
    while (running) {
        if (uart_fd == -1) {
            usleep(100000);
            continue;
        }
        
        ssize_t n = read(uart_fd, buffer + buffer_len, sizeof(buffer) - buffer_len);
        if (n > 0) {
            buffer_len += n;
            
            while (buffer_len >= 4) {
                if (!waiting_for_packet) {
                    const uint8_t *found_seq = NULL;
                    int pos = find_start_sequence(buffer, buffer_len, &found_seq);
                    
                    if (pos == -1) {
                        if (buffer_len > 64) {
                            printf("No start sequence found. Discarding first 10 bytes.\n");
                            memmove(buffer, buffer + 10, buffer_len - 10);
                            buffer_len -= 10;
                        } else {
                            break;
                        }
                    } else {
                        if (pos > 0) {
                            memmove(buffer, buffer + pos, buffer_len - pos);
                            buffer_len -= pos;
                        }
                        
                        expected_packet_start = found_seq;
                        waiting_for_packet = true;
                        printf("Start sequence found (type: %02X%02X%02X%02X), buffer_len=%zu\n",
                               found_seq[0], found_seq[1], found_seq[2], found_seq[3], buffer_len);
                    }
                }
                
                if (waiting_for_packet && buffer_len >= PACKET_SIZE) {
                    if (!compare_start_seq(buffer, expected_packet_start, 4)) {
                        printf("Unexpected packet start, resetting search\n");
                        waiting_for_packet = false;
                        expected_packet_start = NULL;
                        memmove(buffer, buffer + 1, buffer_len - 1);
                        buffer_len--;
                        continue;
                    }
                    
                    process_complete_packet(buffer, expected_packet_start);
                    
                    memmove(buffer, buffer + PACKET_SIZE, buffer_len - PACKET_SIZE);
                    buffer_len -= PACKET_SIZE;
                    waiting_for_packet = false;
                    expected_packet_start = NULL;
                } else {
                    break;
                }
            }
        } else if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            fprintf(stderr, "UART read error: %s\n", strerror(errno));
            usleep(100000);
        }
        
        usleep(10000);
    }
    
    return NULL;
}

void build_uart_packet_temperature(uint8_t command, uint8_t *packet) {
    const uint8_t DATA_PAYLOAD = 55;
    const uint8_t RESP_OK = 0x00;
    
    uint8_t payload[DATA_PAYLOAD];
    memset(payload, 0, DATA_PAYLOAD);
    
    uint8_t buffer_crc[3 + DATA_PAYLOAD];
    buffer_crc[0] = command;
    buffer_crc[1] = RESP_OK;
    buffer_crc[2] = 0;
    memcpy(&buffer_crc[3], payload, DATA_PAYLOAD);
    
    uint16_t crc_val = calc_crc16(buffer_crc, sizeof(buffer_crc));
    uint8_t crc_hi = (crc_val >> 8) & 0xFF;
    uint8_t crc_lo = crc_val & 0xFF;
    
    memcpy(packet, START_SEQ_TEMPERATURE, 4);
    packet[4] = command;
    packet[5] = RESP_OK;
    packet[6] = 0;
    memcpy(&packet[7], payload, DATA_PAYLOAD);
    packet[62] = crc_hi;
    packet[63] = crc_lo;
}

void build_uart_packet_traction(uint8_t command, uint8_t *packet) {
    const uint8_t DATA_PAYLOAD = 55;
    const uint8_t RESP_OK = 0x00;
    
    uint8_t payload[DATA_PAYLOAD];
    memset(payload, 0, DATA_PAYLOAD);
    
    uint8_t buffer_crc[3 + DATA_PAYLOAD];
    buffer_crc[0] = command;
    buffer_crc[1] = RESP_OK;
    buffer_crc[2] = 0;
    memcpy(&buffer_crc[3], payload, DATA_PAYLOAD);
    
    uint16_t crc_val = calc_crc16(buffer_crc, sizeof(buffer_crc));
    uint8_t crc_hi = (crc_val >> 8) & 0xFF;
    uint8_t crc_lo = crc_val & 0xFF;
    
    memcpy(packet, START_SEQ_TRACTION, 4);
    packet[4] = command;
    packet[5] = RESP_OK;
    packet[6] = 0;
    memcpy(&packet[7], payload, DATA_PAYLOAD);
    packet[62] = crc_hi;
    packet[63] = crc_lo;
}

void build_uart_packet_high_temperature(uint8_t command, uint8_t *packet) {
    const uint8_t DATA_PAYLOAD = 55;
    const uint8_t RESP_OK = 0x00;
    
    uint8_t payload[DATA_PAYLOAD];
    memset(payload, 0, DATA_PAYLOAD);
    
    uint8_t buffer_crc[3 + DATA_PAYLOAD];
    buffer_crc[0] = command;
    buffer_crc[1] = RESP_OK;
    buffer_crc[2] = 0;
    memcpy(&buffer_crc[3], payload, DATA_PAYLOAD);
    
    uint16_t crc_val = calc_crc16(buffer_crc, sizeof(buffer_crc));
    uint8_t crc_hi = (crc_val >> 8) & 0xFF;
    uint8_t crc_lo = crc_val & 0xFF;
    
    memcpy(packet, START_SEQ_HIGH_TEMPERATURE, 4);
    packet[4] = command;
    packet[5] = RESP_OK;
    packet[6] = 0;
    memcpy(&packet[7], payload, DATA_PAYLOAD);
    packet[62] = crc_hi;
    packet[63] = crc_lo;
}

void* periodic_send_thread(void* arg) {
    const char *ports[] = {"/dev/ttyUSB1", "/dev/ttyUSB0", "/dev/ttyUSB3"};
    
    for (int i = 0; i < 3; i++) {
        uart_fd = uart_init(ports[i]);
        if (uart_fd != -1) {
            printf("UART connection established on %s\n", ports[i]);
            break;
        }
    }
    
    if (uart_fd == -1) {
        fprintf(stderr, "Failed to open any UART port\n");
        return NULL;
    }
    
    sleep(2);
    uint8_t packet[PACKET_SIZE];
    
    build_uart_packet_temperature(0x3A, packet);
    pthread_mutex_lock(&uart_mutex);
    ssize_t written = write(uart_fd, packet, PACKET_SIZE);
    pthread_mutex_unlock(&uart_mutex);
    printf("Sent initial temperature packet (%zd bytes)\n", written);
    
    sleep(3);
    
    while (running) {
        pthread_mutex_lock(&uart_mutex);
        build_uart_packet_temperature(0x3B, packet);
        written = write(uart_fd, packet, PACKET_SIZE);
        pthread_mutex_unlock(&uart_mutex);
        printf("Temperature command sent (%zd bytes)\n", written);
        sleep(1);
        
        pthread_mutex_lock(&uart_mutex);
        build_uart_packet_traction(0x3B, packet);
        written = write(uart_fd, packet, PACKET_SIZE);
        pthread_mutex_unlock(&uart_mutex);
        printf("Traction command sent (%zd bytes)\n", written);
        sleep(1);
        
        pthread_mutex_lock(&uart_mutex);
        build_uart_packet_high_temperature(0x3B, packet);
        written = write(uart_fd, packet, PACKET_SIZE);
        pthread_mutex_unlock(&uart_mutex);
        printf("High_Temperature command sent (%zd bytes)\n", written);
        sleep(1);
    }
    
    return NULL;
}

void signal_handler(int sig) {
    printf("\nReceived signal %d, shutting down...\n", sig);
    running = false;
}

int main() {
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    curl_global_init(CURL_GLOBAL_DEFAULT);
    
    pthread_t reader_thread, sender_thread;
    
    printf("Starting UART application...\n");
    
    if (pthread_create(&reader_thread, NULL, uart_reader_thread, NULL) != 0) {
        fprintf(stderr, "Error creating reader thread\n");
        curl_global_cleanup();
        return 1;
    }
    
    if (pthread_create(&sender_thread, NULL, periodic_send_thread, NULL) != 0) {
        fprintf(stderr, "Error creating sender thread\n");
        running = false;
        pthread_join(reader_thread, NULL);
        curl_global_cleanup();
        return 1;
    }
    
    pthread_join(reader_thread, NULL);
    pthread_join(sender_thread, NULL);
    
    if (uart_fd != -1) {
        close(uart_fd);
    }
    pthread_mutex_destroy(&uart_mutex);
    curl_global_cleanup();
    
    printf("Program exited cleanly\n");
    return 0;
}