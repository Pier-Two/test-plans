#!/bin/bash
# Build Docker images for all implementations defined in impls.yaml
# Uses content-addressed caching under $CACHE_DIR/snapshots/
# Supports github, local, and browser source types

set -euo pipefail

# Configuration
CACHE_DIR="${CACHE_DIR:-/srv/cache}"
FILTER="${1:-}"  # Optional: pipe-separated filter (e.g., "rust-v0.56|rust-v0.55")
REMOVE="${2:-false}"  # Remove the docker image if set

echo "  → Cache directory: $CACHE_DIR"
if [ -n "$FILTER" ]; then
    echo "  → Filter: $FILTER"
fi

# Ensure cache directory exists
mkdir -p "$CACHE_DIR/snapshots"

# Parse impls.yaml and build each implementation
impl_count=$(yq eval '.implementations | length' impls.yaml)

for ((i=0; i<impl_count; i++)); do
    # Extract implementation details
    impl_id=$(yq eval ".implementations[$i].id" impls.yaml)
    source_type=$(yq eval ".implementations[$i].source.type" impls.yaml)
    requires_submodules=$(yq eval ".implementations[$i].source.requiresSubmodules // false" impls.yaml)

    # Apply filter if specified (exact match only, not substring)
    if [ -n "$FILTER" ] && [[ ! "$impl_id" =~ ^($FILTER)$ ]]; then
        continue  # Skip silently
    fi

    # Check if image already exists
    if docker image inspect "$impl_id" &> /dev/null; then
        if [ "$REMOVE" = "true" ]; then
            echo "  → Forcing rebuild of $impl_id"
            docker rmi "$impl_id" &> /dev/null || echo "Tried to remove non-existent image"
        else
            echo "  ✓ $impl_id (already built)"
            continue
        fi
    fi

    echo ""
    echo "╲ Building: $impl_id"
    echo " ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔"
    echo "→ Type: $source_type"

    case "$source_type" in
        github)
            # GitHub source type
            repo=$(yq eval ".implementations[$i].source.repo" impls.yaml)
            commit=$(yq eval ".implementations[$i].source.commit" impls.yaml)
            dockerfile=$(yq eval ".implementations[$i].source.dockerfile" impls.yaml)
            build_context=$(yq eval ".implementations[$i].source.buildContext" impls.yaml)
            repo_slug=${repo//\//_}

            echo "→ Repo: $repo"
            echo "→ Commit: ${commit:0:8}"

            # Download snapshot if not cached
            if [ "$requires_submodules" = "true" ]; then
                snapshot_file="$CACHE_DIR/snapshots/${repo_slug}-${commit}.tar.gz"
            else
                snapshot_file="$CACHE_DIR/snapshots/$commit.zip"
            fi

            if [ ! -f "$snapshot_file" ]; then
                if [ "$requires_submodules" = "true" ]; then
                    echo "  → [MISS] Cloning snapshot (with submodules)..."
                    tmp_dir=$(mktemp -d)
                    repo_dir="$tmp_dir/${repo_slug}-${commit}"
                    mkdir -p "$repo_dir"
                    git init "$repo_dir" >/dev/null
                    git -C "$repo_dir" remote add origin "https://github.com/$repo.git"
                    git -C "$repo_dir" fetch --depth 1 origin "$commit" >/dev/null 2>&1 || git -C "$repo_dir" fetch origin "$commit" >/dev/null 2>&1
                    git -C "$repo_dir" checkout --quiet FETCH_HEAD
                    git -C "$repo_dir" submodule update --init --recursive
                    rm -rf "$repo_dir/.git"
                    tar -czf "$snapshot_file" -C "$tmp_dir" "${repo_slug}-${commit}"
                    rm -rf "$tmp_dir"
                else
                    echo "  → [MISS] Downloading snapshot..."
                    repo_url="https://github.com/$repo/archive/$commit.zip"
                    wget -O "$snapshot_file" "$repo_url" || {
                        echo "✗ Failed to download snapshot"
                        exit 1
                    }
                fi
                echo "  ✓ Added to cache: $(basename "$snapshot_file")"
            else
                echo "  ✓ [HIT] Using cached snapshot: $(basename "$snapshot_file")"
            fi

            repo_name=$(basename "$repo")

            # Check if using local build context
            if [ "$build_context" = "local" ]; then
                work_dir="impls/${impl_id//-//}"  # Convert python-v0.4 to impls/python/v0.4

                if [ ! -d "$work_dir" ]; then
                    echo "✗ Working dir not found: $work_dir"
                    exit 1
                fi

                # Remove old extracted snapshot if it exists
                rm -rf "$work_dir/$repo_name-"*

                extracted_dir="$work_dir"
            else
                # Extract snapshot to temporary directory
                work_dir=$(mktemp -d)
                trap "rm -rf $work_dir" EXIT
                extracted_dir="$work_dir/$repo_name-$commit"
            fi

            echo "→ Extracting snapshot to: ${work_dir}"
            if [[ "$snapshot_file" == *.zip ]]; then
                unzip -q "$snapshot_file" -d "$work_dir"
            else
                tar -xzf "$snapshot_file" -C "$work_dir"
            fi

            if [ ! -d "$work_dir/$repo_name-$commit" ] && [ ! -d "$work_dir/${repo_slug}-${commit}" ]; then
                echo "✗ Expected directory not found: $work_dir/$repo_name-$commit"
                exit 1
            fi

            # Build Docker image
            echo "→ Building Docker image..."
            if [ ! -d "$extracted_dir" ]; then
                extracted_dir="$work_dir/${repo_slug}-${commit}"
            fi
            if ! docker build -f "$extracted_dir/$dockerfile" -t "$impl_id" "$extracted_dir"; then
                echo "✗ Docker build failed"
                exit 1
            fi

            # Cleanup extracted snapshot
            echo "→ Cleaning up extracted snapshot..."
            rm -rf "$work_dir/$repo_name-$commit" "$work_dir/${repo_slug}-${commit}"
            trap - EXIT
            ;;

        local)
            # Local source type
            local_path=$(yq eval ".implementations[$i].source.path" impls.yaml)
            dockerfile=$(yq eval ".implementations[$i].source.dockerfile" impls.yaml)

            echo "  Path: $local_path"

            if [ ! -d "$local_path" ]; then
                echo "✗ Local path not found: $local_path"
                exit 1
            fi

            echo "→ Building Docker image from local source..."
            if ! docker build -f "$local_path/$dockerfile" -t "$impl_id" "$local_path"; then
                echo "✗ Docker build failed"
                exit 1
            fi
            ;;

        browser)
            # Browser source type
            base_image=$(yq eval ".implementations[$i].source.baseImage" impls.yaml)
            browser=$(yq eval ".implementations[$i].source.browser" impls.yaml)
            dockerfile=$(yq eval ".implementations[$i].source.dockerfile" impls.yaml)

            echo "  Base: $base_image"
            echo "  Browser: $browser"

            # Ensure base image exists
            if ! docker image inspect "$base_image" &> /dev/null; then
                echo "✗ Base image not found: $base_image"
                echo "  Please build $base_image first"
                exit 1
            fi

            # Tag base image for browser build
            echo "→ Tagging base image..."
            docker tag "$base_image" "node-$base_image"

            # Build browser image
            echo "→ Building browser Docker image..."
            dockerfile_dir=$(dirname "$dockerfile")
            if ! docker build \
                -f "$dockerfile" \
                --build-arg BASE_IMAGE="node-$base_image" \
                --build-arg BROWSER="$browser" \
                -t "$impl_id" \
                "$dockerfile_dir"; then
                echo "✗ Docker build failed"
                exit 1
            fi
            ;;

        *)
            echo "✗ Unknown source type: $source_type"
            exit 1
            ;;
    esac

    # Get image ID
    image_id=$(docker image inspect "$impl_id" -f '{{.Id}}' | cut -d':' -f2)
    echo "✓ Built: $impl_id"
    echo "✓ Image ID: ${image_id:0:12}..."
done

echo ""
echo "✓ All required images built successfully"
