#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>
#include <termios.h>
#include <signal.h>

volatile sig_atomic_t stop = 0;

void handle_signal(int signal) {
    if (signal == SIGINT) {
        stop = 1;
        printf("\nПрограмма остановлена пользователем.\n");
    }
}

int main() {
    const char *portname = "/dev/ttyUSB0";
    int fd;

    fd = open(portname, O_RDWR | O_NOCTTY | O_SYNC);
    if (fd < 0) {
        fprintf(stderr, "Ошибка открытия порта %s: %s\n", portname, strerror(errno));
        return EXIT_FAILURE;
    }

    struct termios tty;
    if (tcgetattr(fd, &tty) < 0) {
        fprintf(stderr, "Ошибка получения параметров порта: %s\n", strerror(errno));
        close(fd);
        return EXIT_FAILURE;
    }

    cfsetospeed(&tty, B9600);
    cfsetispeed(&tty, B9600);

    tty.c_cflag &= ~PARENB;  
    tty.c_cflag &= ~CSTOPB;  
    tty.c_cflag &= ~CSIZE;   
    tty.c_cflag |= CS8;     
#ifdef CRTSCTS
    tty.c_cflag &= ~CRTSCTS; 
#endif
    tty.c_cflag |= CREAD | CLOCAL; 

    tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG); 
    tty.c_iflag &= ~(IXON | IXOFF | IXANY); 
    tty.c_oflag &= ~OPOST;

    if (tcsetattr(fd, TCSANOW, &tty) < 0) {
        fprintf(stderr, "Ошибка настройки параметров порта: %s\n", strerror(errno));
        close(fd);
        return EXIT_FAILURE;
    }

    signal(SIGINT, handle_signal);

    printf("Программа запущена. Нажмите Ctrl+C для остановки.\n");

    while (!stop) {
        const char *command = "MEAS?\n";
        if (write(fd, command, strlen(command)) < 0) {
            fprintf(stderr, "Ошибка отправки команды: %s\n", strerror(errno));
            break;
        }

        char buffer[256];
        int n = read(fd, buffer, sizeof(buffer) - 1);
        if (n < 0) {
            fprintf(stderr, "Ошибка чтения данных: %s\n", strerror(errno));
            break;
        }
        buffer[n] = '\0';

        printf("Данные в HEX: ");
        for (int i = 0; i < n; i++) {
            printf("%02X ", (unsigned char)buffer[i]);
        }
        printf("\n");

        printf("Данные как текст: %s\n", buffer);

        sleep(1);
    }

    close(fd);
    printf("Программа завершена.\n");
    return EXIT_SUCCESS;
}