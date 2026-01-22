(input-params)=

# Input Parameters

MOM6 behavior is controlled through parameter files (namelists) and the diagnostic table. CrocoDash uses CESM's MOM_interface to generate these files with sensible defaults.

## Generated Files

When you run case preview (or setup), CESM generates several MOM6 configuration files:

- **`MOM_input`** - Main namelist controlling MOM6 parameters
- **`diag_table`** - Diagnostic output configuration
- **`others`** 

These files are initially placed in the case's `CaseDocs` directory for reference.

## How Defaults Are Generated

1. **MOM_interface** - CESM's bridge component for MOM6
   - Located in: `components/mom` in CESM sandboxes
   - Generates default files based on grid and component settings
   - Files generated via `preview_namelists()` which calls MOM_interface to validate and generate files

2. **Default Recommendations** - CrocoDash (and the %REGIONAL compset) provides tested defaults
   - Grid-aware settings (domain size, resolution)
   - Physics settings appropriate for regional domains
   - Diagnostic settings for common use cases

## Customizing Parameters

There are two approaches to customizing MOM6 parameters:

### 1. User Namelist Modifications (What you should use!)

Override specific parameters using `user_nl_mom`:

```bash
# In your case directory user_nl_mom 
DT_BAROCLINIC = 1800  ! Change timestep
TIDES = TRUE  ! Enable tides (internal)

```

Then regenerate namelists:
```bash
./preview_namelists
```

**Advantages:**
- Clean, trackable changes
- Easy to see what you modified
- Plays well with CESM workflows
- Can be included in case scripts

### 2. SourceMods Overrides

For more extensive customization (whole file replacement):

1. **Generate the default file:**
   ```bash
   ./preview_namelists
   ```

2. **Copy to SourceMods:**
   ```bash
   cp CaseDocs/MOM_input SourceMods/src.mom/
   cp CaseDocs/diag_table SourceMods/src.mom/
   ```

3. **Edit the files in SourceMods:**
   ```bash
   # Edit SourceMods/src.mom/MOM_input as needed
   # Edit SourceMods/src.mom/diag_table as needed
   ```

**Advantages:**
- Complete control over file contents
- Good for major parameter changes

**Disadvantages:**
- Can miss updates to defaults
- Less transparent about what changed

## Viewing Generated Files

After running `preview_namelists`, check:

```bash
# View generated defaults
cat CaseDocs/MOM_input
cat CaseDocs/diag_table

# View your modifications
cat user_nl_mom
cat SourceMods/src.mom/MOM_input  # if using SourceMods
```

## Common Customizations

### Change Model Timestep
```bash
echo "DT_BAROCLINIC = 1800" >> user_nl_mom
```

### Adjust Diagnostic Output Frequency
Edit `diag_table` to change output intervals or variables.


## Verifying Your Configuration

After making changes, verify everything is correct:

```bash
# Check that preview passes
./preview_namelists

# Examine modified files in CaseDocs
cat CaseDocs/MOM_input

# Build to catch any compilation issues
./case.build
```

## Parameter Documentation

For detailed information about MOM6 parameters:

- **MOM6 Manual:** [https://mom6.readthedocs.io/](https://mom6.readthedocs.io/)
- **MOM6 Parameters:** MOM_input file comments and MOM6 documentation
- **CESM MOM_interface:** See CESM documentation for default coupling parameters

## Integration with CrocoDash

When using CrocoDash, parameter customization happens after case creation:

1. **CrocoDash creates the case and adjusts parameters** with grid and forcing configurations
2. **You customize parameters beyond CrocoDash** via user_nl_mom or SourceMods
3. **You build and run the case** with modified parameters

For configuration of forcing-specific parameters (tides, BGC, rivers, etc.), see [Forcing Configuration](forcing_configurations.md) instead.

## Tips and Best Practices

- **Start with defaults** - CrocoDash provides tested defaults; modify only what you need
- **Document your changes** - Add comments to user_nl_mom explaining why you changed things
- **Check compatibility** - Some parameters interact; changing one may require changing others

## Troubleshooting

**"preview_namelists failed"**
- Check user_nl_mom syntax (must be valid Fortran namelist format)
- Ensure parameter names are spelled correctly
- Look for duplicate parameter definitions



You do not need to rebuild your case with parameter changes!!!