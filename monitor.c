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

struct process
{
    int pid;
    unsigned long start;
    unsigned long end;
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

char *get_username_from_uid(int pid)
{
    char path[512];
    int uid = -1;
    
    snprintf(path, sizeof(path), "/proc/%d/status", pid);
    FILE *status_file = fopen(path, "r");
    if (status_file == NULL)
    {
        return NULL;
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
    if (pw == NULL)
        return NULL;
    
    // Make a copy of the username string to avoid it being overwritten
    char *username = malloc(strlen(pw->pw_name) + 1);
    if (username != NULL)
        strcpy(username, pw->pw_name);
    
    return username;
}

unsigned long get_process_cpu_time(int pid)
{
    char path[512];
    long ticks_per_sec = sysconf(_SC_CLK_TCK);

    snprintf(path, sizeof(path), "/proc/%d/stat", pid);
    FILE *stat_file = fopen(path, "r");
    if (stat_file == NULL)
    {
        return -1;
    }

    char comm[256];
    char state;
    unsigned long utime, stime;
    fscanf(stat_file, "%*d %s %c", comm, &state);
    for(int j = 0; j < 10; j++)
    {
        fscanf(stat_file, "%*s");
    }
    fscanf(stat_file, "%lu %lu", &utime, &stime);
    fclose(stat_file);

    unsigned long time_in_ms = (utime + stime) * 1000 / ticks_per_sec;
    
    return time_in_ms;
}


int main(int argc, char *argv[])
{
    if (argc != 2) 
    {
        fprintf(stderr, "Usage: %s <seconds>\n", argv[0]);
        return EXIT_FAILURE;
    }

    int duration = atoi(argv[1]); 

    // Open the /proc directory 
    DIR *proc_dir = opendir("/proc");
    if (proc_dir == NULL) 
    {
        perror("Failed to open /proc");
        return EXIT_FAILURE;
    }

    struct process processes[1024];
    int process_count = 0;
    while(duration > 0)
    {
        rewinddir(proc_dir);  // Go back to start of /proc

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

                    int pid = atoi(name);
                    unsigned long cpu_time = get_process_cpu_time(pid);
                    if((long)cpu_time == -1)
                    {
                        continue;
                    }
                    int exists = 0;
                    for (int j = 0; j < process_count; j++)
                    {
                        if (processes[j].pid == pid)
                        {
                            processes[j].end = cpu_time;
                            exists = 1;
                            break;
                        }
                    }
                    if(!exists)
                    {
                        processes[process_count].pid = pid;
                        processes[process_count].start = cpu_time;
                        processes[process_count].end = processes[process_count].start;
                        process_count++;
                    }
                }
            }
            else
            {
                continue;
            }
        }
        sleep(1);
        duration--;
    }
    closedir(proc_dir);

    struct user users[1024];
    int user_count = 0;
    for(int i = 0; i < process_count; i++)
    {
        char *username = get_username_from_uid(processes[i].pid);
        if(username == NULL)
        {
            continue;
        }
        int exists = 0;
        for (int j = 0; j < user_count; j++)
        {
            if (strcmp(users[j].name, username) == 0)
            {
                users[j].cpu_time += processes[i].end - processes[i].start;
                exists = 1;
                break;
            }
        }
        if(!exists)
        {
            users[user_count].cpu_time = processes[i].end - processes[i].start;
            strncpy(users[user_count].name, username, sizeof(users[user_count].name) - 1);
            users[user_count].name[sizeof(users[user_count].name) - 1] = '\0';
            user_count++;
        }
    }

    qsort(users, user_count, sizeof(struct user), compare_users);
    printf("%-6s %-20s %s\n", "Rank", "User", "CPU Time (milliseconds)");
    printf("----------------------------------------\n");
    for (int i = 0; i < user_count; i++) 
    {
        printf("%-6d %-20s %lu\n", i + 1, users[i].name, users[i].cpu_time);
    }

    // Free allocated memory for usernames
    for (int i = 0; i < process_count; i++)
    {
        char *username = get_username_from_uid(processes[i].pid);
        if (username != NULL)
            free(username);
    }

    return EXIT_SUCCESS;
}