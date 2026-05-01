<#if package?? && package != "">
package ${package};

 </#if>
<#if methodTearDown!false>
import org.junit.jupiter.api.AfterEach;
</#if>
<#if classTearDown!false>
import org.junit.jupiter.api.AfterAll;
</#if>
<#if methodSetUp!false>
import org.junit.jupiter.api.BeforeEach;
</#if>
<#if classSetUp!false>
import org.junit.jupiter.api.BeforeAll;
</#if>
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
 
public class ${name} {

  @Test
  void ${name}() {
    assertTrue(true);
  }
 <#if classSetUp!false>
    @BeforeAll
    public static void setUpClass() {
    }

 </#if>
<#if classTearDown!false>
    @AfterAll
    public static void tearDownClass() {
    }

 </#if>
<#if methodSetUp!false>
    @BeforeEach
    public void setUp() {
    }

 </#if>
<#if methodTearDown!false>
    @AfterEach
    public void tearDown() {
    }

 </#if>
<#if testMethodsPlaceholder!false>
    // TODO add test methods here.
    // The methods must be annotated with annotation @Test. For example:
    //
    // @Test
    // public void hello() {}

 </#if>
}