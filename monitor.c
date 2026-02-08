#define _GNU_SOURCE

#include <stdio.h>      // fopen, printf, fscanf
#include <stdlib.h>     // atoi, malloc
#include <dirent.h>     // opendir, readdir
#include <string.h>     // strcmp, strncmp
#include <unistd.h>     // sleep, sysconf
#include <pwd.h>        // getpwuid (convert UID to username)
#include <ctype.h>      // isdigit

int main()
{
    int num_users;
    char users[1024][256];
    unsigned long cpu_times[1024];
    
    // Open the /proc directory 
    DIR *proc_dir = opendir("/proc");
    if (proc_dir == NULL) 
    {
        perror("Failed to open /proc");
        return EXIT_FAILURE;
    }

    // Iterate through entries in /proc
    struct dirent *entry;
    while ((entry = readdir(proc_dir)) != NULL)
    {
        if (entry->d_type == DT_DIR)
        {
            char *name = entry->d_name;
            int is_pid = 1;
            int i = 0;
            while (name[i] != '\0')
            {
                if (!isdigit(name[i]))
                {
                    is_pid = 0;
                    break;
                }
                i++;
            }

            if(is_pid)
            {
                char path[512];
                snprintf(path, sizeof(path), "/proc/%s/stat", name);
                FILE *status_file = fopen(path, "r");
                if (status_file == NULL)
                {
                    perror("Failed to open status file");
                    continue;
                }

                int pid;
                char comm[256];
                char state;
                unsigned long utime, stime;
                fscanf(status_file, "%d %s %c", &pid, comm, &state);
                for(int j = 0; j < 10; j++)
                {
                    fscanf(status_file, "%*s");
                }
                fscanf(status_file, "%lu %lu", &utime, &stime);
                printf("PID %d: utime=%lu stime=%lu total=%lu\n", pid, utime, stime, utime + stime);
                fclose(status_file);
            }
        }
        else
        {
            continue;
        }
    }

    closedir(proc_dir);
    return 0;
}