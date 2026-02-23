import os

profiles = [
    r'C:\Users\USER\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1',
    r'C:\Users\USER\Documents\WindowsPowerShell\profile.ps1',
    r'C:\Windows\System32\WindowsPowerShell\v1.0\profile.ps1',
    r'C:\Windows\System32\WindowsPowerShell\v1.0\Microsoft.PowerShell_profile.ps1'
]

for p in profiles:
    if os.path.exists(p):
        print(f"Checking {p}...")
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        if 'sandbox-exec' in content:
            print(f"Found 'sandbox-exec' in {p}. Commenting out...")
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if 'sandbox-exec' in line:
                    new_lines.append('# ' + line)
                else:
                    new_lines.append(line)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            print(f"Fixed {p}.")
        else:
            print(f"No 'sandbox-exec' found in {p}.")
