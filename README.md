# NetBeans — CCT Setup

Shared configuration repository for Java projects in NetBeans.
Provides a zero-clone CLI that configures NetBeans Ant projects automatically.

---

## Prerequisites (once per machine)

Install `uv`:

**Windows (PowerShell):**
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

**Mac / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

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

---

## Global setup (once per machine)

Templates and theme must be imported manually into NetBeans.

### 1. Import settings and theme

- **Settings → Import** → select `templates/Template.zip`

### 2. Install code templates

Open each template in **Tools → Templates** and paste the content of the corresponding file:

| File | Location in NetBeans |
|---|---|
| `ClassTemplate.java` | Java → Java Class |
| `MainClassTemplate.java` | Java → Java Main Class |
| `JUnitTemplate.java` | Test Class → JUnit 5.x → Open in Editor |

---

## JUnit 5 — Common Assertions

```java
import static org.junit.jupiter.api.Assertions.*;

@Test
void exemploAssertions() {

    // assertTrue / assertFalse
    assertTrue(2 + 2 == 4);
    assertFalse(2 + 2 == 5);

    // assertEquals / assertNotEquals
    assertEquals(4, 2 + 2);
    assertNotEquals(5, 2 + 2);

    // with a failure message (shown when the assertion fails)
    assertEquals(4, 2 + 2, "2 + 2 should equal 4");

    // assertNull / assertNotNull
    String name = null;
    assertNull(name);
    assertNotNull("hello");

    // assertThrows — verifies that a method throws an exception
    assertThrows(IllegalArgumentException.class, () -> {
        throw new IllegalArgumentException("invalid input");
    });
}
```

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
│   └── test_setup.py
└── setup.py                      ← CLI entry point (uv PEP 723 script)
```

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
