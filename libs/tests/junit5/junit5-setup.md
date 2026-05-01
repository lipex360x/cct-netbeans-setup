# JUnit 5 — Per-Project Setup (NetBeans + Ant)

> Repeat these steps for every new project created in NetBeans.
> For the global machine setup, see the [`README.md`](../../../README.md) at the repository root.

---

## Required JARs

All files are located in `libs/tests/junit5/jar/`:

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

---

## Step 1 — Add JARs to the project

- Right-click the project → **Properties** → **Libraries**
- **Compile Tests** tab:
  - Click **+** next to Classpath → **Add JAR/Folder**
  - Select all 9 `.jar` files from `libs/tests/junit5/jar/`
- Repeat the same steps on the **Run Tests** tab
- Click **OK**

## Step 2 — Disable Compile on Save

- Still in **Properties** → **Build** → **Compiling**
- Uncheck **Compile on Save**
- Click **OK**

## Step 3 — Override the test runner in build.xml

NetBeans uses the JUnit 4 runner by default. The targets below replace that behavior and enable `junitlauncher`, the correct runner for JUnit 5.

- Switch to the **Files** tab in the left panel, open `build.xml`
- Copy the full content of `junit5-build-override.xml`
- Paste it immediately **after** this line:
  ```xml
  <import file="nbproject/build-impl.xml"/>
  ```
- Save the file

## Step 4 — Validate the setup

- Switch back to the **Projects** tab
- Right-click **Test Packages** → **New** → **JUnit Test**
- Create a `SanityTest` class with the test below:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SanityTest {

  @Test
  void sanityCheck() {
    assertTrue(true);
  }
}
```

- Right-click the file → **Test File**
- Green bar = setup is working
