if [ "$#" -ne 2 ]; then
    (>&2 echo "Usage: $0 SOURCE_PDF OUTPUT_PDF\n")
    exit 1
fi

SOURCE=$1
OUTPUT=$2

BRANCH_NAME=PolyglotBranch

git ls-files $OUTPUT --error-unmatch 1>/dev/null 2>&1
if [ $? -ne 1 ]; then
    (>&2 echo "Error: The output file $OUTPUT is already tracked by git!\n       This will not work! Please choose another output file.\n")
    exit 2
fi

git rev-parse --verify $BRANCH_NAME 1>/dev/null 2>&1
if [ $? -eq 0 ]; then
    (>&2 echo "Error: A branch named $BRANCH_NAME already exists!\n       You need to either delete this branch\n       or set a different value for the BRANCH_NAME variable\n       in $0\n")
    exit 3
fi

CURRENT_BRANCH=`git rev-parse --abbrev-ref HEAD`

cp $SOURCE $OUTPUT

rm -f ${OUTPUT}.log

git stash save MAKINGPOLYGLOT 1>>${OUTPUT}.log 2>&1
git stash list | grep -q MAKINGPOLYGLOT
HAS_STASH=$?

if [ $HAS_STASH -eq 0 ]; then
    echo "There are local changes! Saving them to a stash so they are not lost..."
fi

echo "Creating temporary branch ${BRANCH_NAME}..."
git checkout -b $BRANCH_NAME
if [ $HAS_STASH -eq 0 ]; then
    echo "Applying the stash to the new branch..."
    git stash apply 1>>${OUTPUT}.log 2>&1
fi
git update-index --add --cacheinfo 100644 `git hash-object -w $OUTPUT` $OUTPUT
TREE_HASH=`git write-tree`
echo 'Polyglot PDF' | git commit-tree $TREE_HASH
git commit -a -m 'Creating the Polyglot'
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PATH=$DIR:$PATH git bundle create ${OUTPUT}.bundle --do-not-compress `git hash-object $OUTPUT` --all
echo "Switching back to branch ${CURRENT_BRANCH}..."
git checkout $CURRENT_BRANCH 1>>${OUTPUT}.log 2>&1
echo "Deleting temporary branch ${BRANCH_NAME}..."
git branch -D $BRANCH_NAME 1>>${OUTPUT}.log 2>&1
mv ${OUTPUT}.bundle $OUTPUT

if [ $HAS_STASH -eq 0 ]; then
    echo "Re-applying the stash to restore local changes..."
    git stash pop 1>>${OUTPUT}.log 2>&1
fi

echo "Created $OUTPUT"
