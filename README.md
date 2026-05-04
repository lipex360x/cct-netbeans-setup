# NetBeans — CCT Setup

> Zero-clone CLI to configure NetBeans Ant projects with JUnit 5, editor preferences, and code templates — no git clone required.

![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![uv](https://img.shields.io/badge/uv-PEP%20723-blueviolet)

---

## Contents

- [Prerequisites](#prerequisites)
- [Per-project setup](#per-project-setup)
- [Global setup](#global-setup)
- [Repository structure](#repository-structure)
- [Included JARs](#included-jars)
- [JUnit 5 — Common Assertions](#junit-5--common-assertions)
- [MySQL — Database Connection](#mysql--database-connection)

---

## Prerequisites

Install `uv` once per machine:

**Windows (PowerShell):**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

**Mac / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> [!TIP]
> If `uv` is already installed, skip this step.

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## Per-project setup

Run from any terminal — no clone required:

**With uv (recommended):**
```bash
uv run "https://raw.githubusercontent.com/lipex360x/cct-netbeans-setup/main/setup.py"
```

**With Python only (if uv is not installed):**
```bash
pip install rich requests
curl -s "https://raw.githubusercontent.com/lipex360x/cct-netbeans-setup/main/setup.py" | python -
```

The script downloads everything it needs and walks you through the options interactively.

The main menu shows `●` next to features already configured in the current project and `○` for features not yet installed:

```
? Select an option:
❯ ● [1] MySQL Database
  ○ [2] JUnit 5
  ● [3] Docker Compose
  ○ [4] .gitignore
    [5] NetBeans Templates
    Quit
```

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## Global setup

Templates and theme can be applied automatically via the script (option **[2] NetBeans Templates**), or manually as described below.

> [!NOTE]
> The script (menu option **[2]**) handles the import automatically. The manual steps below are a fallback for cases where the script cannot detect your NetBeans user directory.

### 1. Import settings and theme

- **Settings → Import** → select `templates/Template.zip`

### 2. Install code templates

Open each template in **Tools → Templates** and paste the content of the corresponding file:

| File | Location in NetBeans |
|---|---|
| `ClassTemplate.java` | Java → Java Class |
| `MainClassTemplate.java` | Java → Java Main Class |
| `JUnitTemplate.java` | Test Class → JUnit 5.x → Open in Editor |

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## Repository structure

```
cct-netbeans-setup/
├── .docs/
│   └── project.yaml              ← project brief and design decisions
├── libs/
│   ├── database/
│   │   └── mysql/
│   │       └── mysql-connector-j.jar
│   └── tests/
│       └── junit5/
│           ├── jar/              ← 9 JUnit 5 JARs (downloaded by setup.py)
│           ├── junit5-build-override.xml
│           └── junit5-setup.md  ← manual setup guide (fallback)
├── templates/
│   ├── Template.zip
│   ├── ClassTemplate.java
│   ├── MainClassTemplate.java
│   ├── JUnitTemplate.java
│   └── templates.md
├── tests/
│   ├── test_setup.py
│   └── test_templates.py
└── setup.py                      ← CLI entry point (uv PEP 723 script)
```

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## Included JARs

### JUnit 5 (`libs/tests/junit5/jar/`)

| JAR | Version |
|---|---|
| `junit-jupiter-api` | 5.10.3 |
| `junit-jupiter-engine` | 5.10.3 |
| `junit-platform-commons` | 1.10.3 |
| `junit-platform-engine` | 1.10.3 |
| `junit-platform-launcher` | 1.10.3 |
| `apiguardian-api` | 1.1.2 |
| `opentest4j` | 1.3.0 |
| `junit` (JUnit 4 compat) | 4.13.2 |
| `hamcrest-core` | 1.3 |

### MySQL (`libs/database/mysql/`)

| JAR | Notes |
|---|---|
| `mysql-connector-j.jar` | Current version in the repository |

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## JUnit 5 — Common Assertions

```java
import static org.junit.jupiter.api.Assertions.*;

class ExampleTest {

    @Test
    void sumReturnsCorrectResult() {
        assertEquals(4, 2 + 2, "2 + 2 should equal 4");
    }

    @Test
    void sumDoesNotReturnWrongResult() {
        assertNotEquals(5, 2 + 2);
    }

    @Test
    void conditionIsTrue() {
        assertTrue(2 + 2 == 4);
    }

    @Test
    void conditionIsFalse() {
        assertFalse(2 + 2 == 5);
    }

    @Test
    void uninitializedValueIsNull() {
        String name = null;
        assertNull(name);
    }

    @Test
    void assignedValueIsNotNull() {
        assertNotNull("hello");
    }

    @Test
    void setAgeThrowsForNegativeValue() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class, () -> setAge(-1));
        assertEquals("Age cannot be negative", ex.getMessage());
    }

    void setAge(int age) {
        if (age < 0) {
            throw new IllegalArgumentException("Age cannot be negative");
        }
    }
}
```

> [!IMPORTANT]
> In `assertThrows`, the lambda must call the method that throws — never wrap the assertion itself inside the lambda.

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>

---

## MySQL — Database Connection

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class DatabaseConnection {

  public static void main(String[] args) {
    String url = "jdbc:mysql://localhost:3306/";
    String database = "database";
    String user = "username";
    String password = "password";

    try {
      Connection conn = DriverManager.getConnection((url + database), user, password);
      System.out.println("Connected to Database " + database);
    } catch (SQLException error) {
      System.out.println("SQL Exception: " + error.getMessage());
    }
  }
}
```

> [!TIP]
> The `mysql-connector-j.jar` is installed automatically by the setup script (option **[1] MySQL Database**). Make sure it is listed in your project's **Libraries** before compiling.

<div align="right"><a href="#netbeans--cct-setup">↑ Back to top</a></div>
