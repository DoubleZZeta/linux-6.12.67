#define _GNU_SOURCE

#include <stdio.h>      // fopen, printf, fscanf
#include <stdlib.h>     // atoi, malloc
#include <dirent.h>     // opendir, readdir
#include <string.h>     // strcmp, strncmp
#include <unistd.h>     // sleep, sysconf
#include <pwd.h>        // getpwuid (convert UID to username)
#include <ctype.h>      // isdigit

struct user
{
    char name[256];
    unsigned long cpu_time;
    
};

int compare_users(const void *a, const void *b) {
    struct user *ua = (struct user *)a;
    struct user *ub = (struct user *)b;
    
    // Descending order (highest first)
    if (ub->cpu_time > ua->cpu_time)
    {
        return 1;
    }
    if (ub->cpu_time < ua->cpu_time)
    {
        return -1;
    }
    return 0;
}

unsigned long get_process_cpu_time(char* name)
{
    char path[512];
    long ticks_per_sec = sysconf(_SC_CLK_TCK);

    snprintf(path, sizeof(path), "/proc/%s/stat", name);
    FILE *stat_file = fopen(path, "r");
    if (stat_file == NULL)
    {
        perror("Failed to open status file");
        return 0;
    }

    int pid;
    char comm[256];
    char state;
    unsigned long utime, stime;
    fscanf(stat_file, "%d %s %c", &pid, comm, &state);
    for(int j = 0; j < 10; j++)
    {
        fscanf(stat_file, "%*s");
    }
    fscanf(stat_file, "%lu %lu", &utime, &stime);
    fclose(stat_file);

    unsigned long time_in_ms = (utime + stime) * 1000 / ticks_per_sec;
    
    return time_in_ms;
}

char *get_username_from_uid(char *name)
{
    char path[512];
    int uid = -1;
    
    snprintf(path, sizeof(path), "/proc/%s/status", name);
    FILE *status_file = fopen(path, "r");
    if (status_file == NULL)
    {
        perror("Failed to open status file");
        return 0;
    }

    char line[256];
    while (fgets(line, sizeof(line), status_file))
    {
        if (strncmp(line, "Uid:", 4) == 0)
        {
            sscanf(line, "Uid:\t%d", &uid);
            break;
        }
    }
    fclose(status_file);

    struct passwd *pw = getpwuid(uid);
    char *username = pw ? pw->pw_name : "unknown"; // need to revise 
    return username;
}


int main(int argc, char *argv[])
{
    if (argc != 2) 
    {
        fprintf(stderr, "Usage: %s <seconds>\n", argv[0]);
        return EXIT_FAILURE;
    }

    int duration = atoi(argv[1]); 
    int num_users;
    struct user users[1024];
    int user_count = 0;
    
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
                char *username = get_username_from_uid(name);
                unsigned long cpu_time = get_process_cpu_time(name);

                int exists = 0;
                for (int j = 0; j < user_count; j++)
                {
                    if (strcmp(users[j].name, username) == 0)
                    {
                        users[j].cpu_time += cpu_time;
                        exists = 1;
                        break;
                    }
                }
                if (!exists) // new user
                {
                    strncpy(users[user_count].name, username, sizeof(users[user_count].name) - 1);
                    users[user_count].name[sizeof(users[user_count].name) - 1] = '\0';
                    users[user_count].cpu_time = cpu_time;
                    user_count++;
                }
            }
        }
        else
        {
            continue;
        }
    }

    qsort(users, user_count, sizeof(struct user), compare_users);
    printf("%-6s %-20s %s\n", "Rank", "User", "CPU Time (milliseconds)");
    printf("----------------------------------------\n");
    for (int i = 0; i < user_count; i++) {
        printf("%-6d %-20s %lu\n", i + 1, users[i].name, users[i].cpu_time);
    }

    closedir(proc_dir);
    return 0;
}