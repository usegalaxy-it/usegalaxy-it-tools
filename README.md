# usegalaxy.it-tools-reports
Repository to store reports about updated/installed tools in Usegalaxy.it

## Submodule instructions

### Cloning the repository
1. Cloning for the first time

    To clone this repository including its submodules, run:

    ```
    git clone --recurse-submodules <url>
    ```

2. If already cloned without the submodule

    Initialize the submodule, run:
    ```
    git submodule init
    git submodule update
    ```

### Updating usegalaxy-eu-tools submodule
1. Inside the root repository run the following command:

    ```
    git submodule update --remote --merge
    ```
2. Stage the changes

    ```
    git add usegalaxy-eu-tools/
    ```
3. Commit and push

    ```
    git commit -m "Update usegalaxy-eu-tools to latest commit"
    git push
    ```
    
