#define _GNU_SOURCE

#include <stdio.h>      // fopen, printf, fscanf
#include <stdlib.h>     // atoi, malloc
#include <dirent.h>     // opendir, readdir
#include <string.h>     // strcmp, strncmp
#include <unistd.h>     // sleep, sysconf
#include <pwd.h>        // getpwuid (convert UID to username)
#include <ctype.h>      // isdigit

unsigned long get_process_cpu_time(char* name)
{
    char path[512];
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
    
    return utime + stime;
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

int main()
{
    int num_users;
    char users[1024][256];
    unsigned long cpu_times[1024];
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

                strncpy(users[user_count], username, sizeof(users[user_count]) - 1);
                users[user_count][sizeof(users[user_count]) - 1] = '\0';
                cpu_times[user_count] = cpu_time;
                user_count++;
                
                printf("Process: %s, User: %s, CPU Time: %lu\n", name, username, cpu_time);
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