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
    // Get file descriptor 
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
                print("%d\n", atoi(name));
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