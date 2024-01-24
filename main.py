from time import sleep
from socket import inet_aton, error
import subprocess
import threading

# Netork credentials
domain = ""
username = ""
password = ""

# Settings
inputLocation = "AD HOSTNAME AND IPS.txt"
outputLocation = "computer user ip.txt"
workers = 30 # Both powershell and program threads, keep low
powershellPath = r"C:\Windows\System32\WindowsPowerShell\v1.0"


# Internal Varibles
powershellInstances = []
powershellInstancesFree = []
powershellCreatorLock = threading.Lock()

queryMachineInstances = []
queryMachinesLock = threading.Lock()

workersIndex = 0
completed = 0


def isValidIP(address):
    # IPV4
    try:
        inet_aton(address)
        return True
    except error:
        return False

def cleanStripList(stripList):
    # Stip 0x00 and \n out of lists
    newList = []

    for item in stripList:
        if len(item) != 0 and item != "\n":
            newList.append(item.strip())

    return newList

def createPowershellInstance():
    ps = subprocess.Popen(["powershell.exe"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    sleep(3)
    # Setup network authentication
    ps.stdin.write(f"$Password = ConvertTo-SecureString \"{password}\" -AsPlainText -Force\n")
    ps.stdin.write(f"$Credential = New-Object -TypeName System.Management.Automation.PSCredential -ArgumentList (\"{domain}\\{username}\", $Password)\n")
    ps.stdin.write(f"Write-Host 'ENDOFOUTPUT9'\n")

    ps.stdin.flush()

    while True:
        line = ps.stdout.readline()
        if "ENDOFOUTPUT9" in line and "Write-Host" not in line:
            break
    
    with powershellCreatorLock:
        powershellInstances.append(ps)

def queryMachine(workersIndex, line, outputFile):
    # Assign ps instances and signal that the powershell instance is taken
    with queryMachinesLock:
        ps = powershellInstances[workersIndex]
        powershellInstancesFree[workersIndex] = False

    # Split the line from the file by space and clean it.
    splitLines = cleanStripList(line.split(" "))
    if len(splitLines) >= 2:
        hostname = splitLines[0]
        ip = splitLines[1]

        if not isValidIP(ip):
            print(f"Invalid ip: {ip}")
            return

        # print(hostname, ip) # De bugging

        # Query the machine for the currently logged in user.
        ps.stdin.write(f"Get-WmiObject -ComputerName {hostname} -Class Win32_ComputerSystem -Credential $Credential | Select-Object UserName\n")
        ps.stdin.write("Write-Host 'ENDOFOUTPUT9'\n")
        ps.stdin.flush()

        while True:
            line = ps.stdout.readline()
            if f"{domain}\\" in line:
                with queryMachinesLock:
                    powershellInstancesFree[workersIndex] = True
                    try:
                        username = cleanStripList(line.split(f"{domain}\\"))[0]
                        completed += 1
                    except:
                        pass
                    
                    if not username: return

                    outputFile.write(f"{hostname}\t\t{username}\t\t{ip}")
                break
            if "ENDOFOUTPUT9" in line and "Write-Host" not in line:
                break
        return

with open(outputLocation, "a", encoding="utf-8") as outputFile:
    outputFile.write("\nNEW RUN\n")
    with open(inputLocation, "r", encoding="utf-16") as inputFile:

        # Create powershell instances based on the number of workers the user wants
        print(f"Creating {workers} powershell instances.")

        tempThreads = []
        for i in range(workers):
            t = threading.Thread(target=createPowershellInstance)
            t.start()
            tempThreads.append(t)
            powershellInstancesFree[i] = True
        
        for thread in tempThreads:
            thread.join()
        
        print(f"Created {len(powershellInstances)} powershell instances.")

        for line in inputFile:
            # Rid of stopped threads
            tempThreads2 = []
            for instance in queryMachineInstances:
                if instance.is_alive():
                    tempThreads2.append(instance)
            queryMachineInstances = tempThreads2    

            # Start new thread
            if len(queryMachineInstances) <= workers:
                t = threading.Thread(target=queryMachine, args=(workersIndex, line, outputFile))
                t.start()
                queryMachineInstances.append(t)
                
                # Shift the worker index by 1 to prepare the next worker for a new task
                workersIndex += 1

                if workersIndex >= workers:
                    print(f"Reset workers index. Completed: {completed}")
                    workersIndex = 0

# FORMAT:
"""
Name                                                        ipv4address                                                
----                                                        -----------                                                
HostName                                                    0.0.0.0   
"""
